package com.github.diegopacheco.flinkcassandra;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.stream.Collectors;

public class UiServer {

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(System.getenv().getOrDefault("UI_PORT", "12080"));
        CassandraStore store = new CassandraStore();
        byte[] html;
        try (InputStream in = UiServer.class.getResourceAsStream("/index.html")) {
            html = in.readAllBytes();
        }
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/api/revenue", ex -> {
            try {
                send(ex, 200, "application/json", toJson(store).getBytes(StandardCharsets.UTF_8));
            } catch (RuntimeException e) {
                send(ex, 500, "application/json", ("{\"error\":\"" + String.valueOf(e.getMessage()).replace("\"", "'") + "\"}").getBytes(StandardCharsets.UTF_8));
            }
        });
        server.createContext("/", ex -> {
            if (ex.getRequestURI().getPath().equals("/")) {
                send(ex, 200, "text/html; charset=utf-8", html);
            } else {
                send(ex, 404, "text/plain", "not found".getBytes(StandardCharsets.UTF_8));
            }
        });
        server.start();
        System.out.println("UI listening on http://localhost:" + port);
    }

    private static String toJson(CassandraStore store) {
        return store.findAll().stream()
                .map(s -> String.format(Locale.ROOT, "{\"category\":\"%s\",\"total_orders\":%d,\"total_quantity\":%d,\"total_revenue\":%.2f}", s.category(), s.totalOrders(), s.totalQuantity(), s.totalRevenue()))
                .collect(Collectors.joining(",", "[", "]"));
    }

    private static void send(HttpExchange ex, int status, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(status, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }
}
