package com.github.diegopacheco.temporaletl;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.temporal.client.WorkflowClient;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;

public class UiServer {

    private static final ObjectMapper JSON = new ObjectMapper();

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(Config.get("UI_PORT"));
        String temporalUi = Config.get("TEMPORAL_UI_URL");
        WorkflowClient client = Temporal.client("etl-ui");
        byte[] index;
        try (var in = UiServer.class.getResourceAsStream("/index.html")) {
            index = in.readAllBytes();
        }
        var server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/api/revenue", ex -> json(ex, Db::revenue));
        server.createContext("/api/config", ex -> json(ex, () -> Map.of("temporal_ui", temporalUi, "task_queue", Config.TASK_QUEUE)));
        server.createContext("/api/workflows", ex -> json(ex, () -> HistorySummary.recent(client, 15)));
        server.createContext("/api/workflow", ex -> json(ex, () -> HistorySummary.summarize(client, param(ex, "id"))));
        server.createContext("/", ex -> send(ex, 200, "text/html; charset=utf-8", index));
        server.setExecutor(Executors.newVirtualThreadPerTaskExecutor());
        server.start();
        System.out.println("ui listening on http://localhost:" + port);
    }

    private static String param(HttpExchange ex, String name) {
        String query = ex.getRequestURI().getRawQuery();
        if (query != null) {
            for (var pair : query.split("&")) {
                var kv = pair.split("=", 2);
                if (kv.length == 2 && kv[0].equals(name)) {
                    return URLDecoder.decode(kv[1], StandardCharsets.UTF_8);
                }
            }
        }
        throw new IllegalArgumentException("missing query parameter " + name);
    }

    private static void json(HttpExchange ex, Callable<Object> body) throws IOException {
        try {
            send(ex, 200, "application/json", JSON.writeValueAsBytes(body.call()));
        } catch (Exception e) {
            send(ex, 500, "application/json", JSON.writeValueAsBytes(Map.of("error", String.valueOf(e.getMessage()))));
        }
    }

    private static void send(HttpExchange ex, int status, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(status, body.length);
        try (var out = ex.getResponseBody()) {
            out.write(body);
        }
    }
}
