package eos;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;

public final class UiServer {
    public static void main(String[] args) throws Exception {
        byte[] page = UiServer.class.getResourceAsStream("/index.html").readAllBytes();
        byte[] report = Audit.report().getBytes(StandardCharsets.UTF_8);
        HttpServer server = HttpServer.create(new InetSocketAddress(Settings.UI_PORT), 0);
        server.createContext("/", exchange -> reply(exchange, "text/html; charset=utf-8", page));
        server.createContext("/api/report", exchange -> reply(exchange, "application/json", report));
        server.createContext("/api/events", exchange -> reply(exchange, "application/json", events()));
        server.start();
        System.out.println("ui listening on " + Settings.UI_PORT);
    }

    private static byte[] events() throws IOException {
        return Events.all().stream().map(line -> line.split("\t", 3))
            .map(f -> "{\"time\":" + f[0] + ",\"scenario\":\"" + f[1] + "\",\"message\":\"" + f[2].replace("\\", "\\\\").replace("\"", "\\\"") + "\"}")
            .collect(Collectors.joining(",", "[", "]")).getBytes(StandardCharsets.UTF_8);
    }

    private static void reply(HttpExchange exchange, String type, byte[] body) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", type);
        exchange.sendResponseHeaders(200, body.length);
        exchange.getResponseBody().write(body);
        exchange.close();
    }
}
