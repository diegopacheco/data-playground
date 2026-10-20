package com.github.diegopacheco.cdciceberg;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.stream.Collectors;

public class UiServer {

    private static final List<String> SUMMARY_KEYS = List.of("added-records", "deleted-records", "added-equality-deletes", "added-position-deletes", "total-records", "total-equality-deletes");

    public static void main(String[] args) throws Exception {
        Settings settings = Settings.fromEnv();
        PostgresSource postgres = new PostgresSource(settings);
        IcebergSource iceberg = new IcebergSource(settings);
        byte[] html;
        try (InputStream in = UiServer.class.getResourceAsStream("/index.html")) {
            html = in.readAllBytes();
        }
        HttpServer server = HttpServer.create(new InetSocketAddress(settings.uiPort()), 0);
        server.createContext("/api/compare", json(() -> compare(postgres, iceberg)));
        server.createContext("/api/changes", post(() -> {
            postgres.runScript("changes.sql");
            return "{\"applied\":\"changes.sql\"}";
        }));
        server.createContext("/api/reset", post(() -> {
            postgres.runScript("reset.sql");
            return "{\"applied\":\"reset.sql\"}";
        }));
        server.createContext("/", ex -> {
            if (ex.getRequestURI().getPath().equals("/")) {
                send(ex, 200, "text/html; charset=utf-8", html);
            } else {
                send(ex, 404, "text/plain", "not found".getBytes(StandardCharsets.UTF_8));
            }
        });
        server.start();
        System.out.println("UI listening on http://localhost:" + settings.uiPort());
    }

    private static String compare(PostgresSource postgres, IcebergSource iceberg) throws Exception {
        List<CategoryStats> pgStats = postgres.categoryStats();
        List<OrderRow> pgRows = postgres.rows();
        List<CategoryStats> icebergStats = iceberg.categoryStats().stream()
                .sorted((a, b) -> a.category().compareTo(b.category())).toList();
        List<OrderRow> icebergRows = iceberg.rows();
        List<IcebergSource.Snapshot> snapshots = iceberg.snapshots();

        Set<String> pgPrints = pgRows.stream().map(OrderRow::fingerprint).collect(Collectors.toSet());
        Set<String> icebergPrints = icebergRows.stream().map(OrderRow::fingerprint).collect(Collectors.toSet());
        Set<String> onlyPg = new HashSet<>(pgPrints);
        onlyPg.removeAll(icebergPrints);
        Set<String> onlyIceberg = new HashSet<>(icebergPrints);
        onlyIceberg.removeAll(pgPrints);
        boolean categoriesMatch = stats(pgStats).equals(stats(icebergStats));

        return "{\"postgres\":{\"rows\":" + pgRows.size() + ",\"categories\":" + stats(pgStats) + "},"
                + "\"iceberg\":{\"rows\":" + icebergRows.size() + ",\"categories\":" + stats(icebergStats) + "},"
                + "\"categories_match\":" + categoriesMatch + ","
                + "\"rows_only_in_postgres\":" + onlyPg.size() + ","
                + "\"rows_only_in_iceberg\":" + onlyIceberg.size() + ","
                + "\"in_sync\":" + (categoriesMatch && onlyPg.isEmpty() && onlyIceberg.isEmpty()) + ","
                + "\"snapshots\":" + snapshots.stream().map(UiServer::snapshotJson).collect(Collectors.joining(",", "[", "]")) + "}";
    }

    private static String stats(List<CategoryStats> stats) {
        return stats.stream().map(CategoryStats::toJson).collect(Collectors.joining(",", "[", "]"));
    }

    private static String snapshotJson(IcebergSource.Snapshot s) {
        String summary = SUMMARY_KEYS.stream()
                .map(k -> "\"" + k + "\":" + Long.parseLong(String.valueOf(s.summary() == null || s.summary().get(k) == null ? "0" : s.summary().get(k))))
                .collect(Collectors.joining(","));
        return "{\"snapshot_id\":\"" + s.snapshotId() + "\",\"committed_at\":\"" + s.committedAt() + "\",\"operation\":\"" + s.operation() + "\"," + summary + "}";
    }

    private static HttpHandler json(Callable<String> body) {
        return ex -> {
            try {
                send(ex, 200, "application/json", body.call().getBytes(StandardCharsets.UTF_8));
            } catch (Exception e) {
                e.printStackTrace();
                String msg = String.valueOf(e.getMessage()).replace("\\", "/").replace("\"", "'").replace("\n", " ");
                send(ex, 500, "application/json", ("{\"error\":\"" + msg + "\"}").getBytes(StandardCharsets.UTF_8));
            }
        };
    }

    private static HttpHandler post(Callable<String> body) {
        HttpHandler handler = json(body);
        return ex -> {
            if (!ex.getRequestMethod().equals("POST")) {
                send(ex, 405, "text/plain", "use POST".getBytes(StandardCharsets.UTF_8));
                return;
            }
            handler.handle(ex);
        };
    }

    private static void send(HttpExchange ex, int status, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(status, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }
}
