package bench;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

public class UiServer {

    public static void main(String[] args) throws IOException {
        byte[] html;
        try (InputStream in = UiServer.class.getResourceAsStream("/index.html")) {
            html = in.readAllBytes();
        }
        HttpServer server = HttpServer.create(new InetSocketAddress(Settings.UI_PORT), 0);
        server.createContext("/api/results", UiServer::results);
        server.createContext("/", ex -> send(ex, 200, "text/html; charset=utf-8", html));
        server.start();
        System.out.println("ui listening on http://localhost:" + Settings.UI_PORT);
    }

    private static void results(HttpExchange ex) throws IOException {
        if (Files.exists(Settings.RESULTS)) {
            send(ex, 200, "application/json", Files.readAllBytes(Settings.RESULTS));
        } else {
            send(ex, 404, "application/json", "{\"error\":\"results.json not found, run ./scripts/start-all.sh\"}".getBytes(StandardCharsets.UTF_8));
        }
    }

    private static void send(HttpExchange ex, int status, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(status, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }
}
