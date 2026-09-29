package flight;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Executors;

public final class CsvHttpServer implements AutoCloseable {

    private final HttpServer server;

    public CsvHttpServer(int port, Path benchCsv) throws IOException {
        server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/bench.csv", exchange -> sendFile(exchange, benchCsv));
        server.createContext("/health", exchange -> sendText(exchange, "ok"));
        server.setExecutor(Executors.newVirtualThreadPerTaskExecutor());
    }

    public void start() {
        server.start();
    }

    private static void sendFile(HttpExchange exchange, Path file) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", "text/csv");
        exchange.sendResponseHeaders(200, Files.size(file));
        try (OutputStream out = exchange.getResponseBody()) {
            Files.copy(file, out);
        }
    }

    private static void sendText(HttpExchange exchange, String text) throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
