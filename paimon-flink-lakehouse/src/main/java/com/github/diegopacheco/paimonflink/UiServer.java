package com.github.diegopacheco.paimonflink;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.types.Row;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.StringJoiner;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Function;

public final class UiServer {

    private static final ExecutorService FLINK = Executors.newSingleThreadExecutor();
    private static final TableEnvironment ENV = init();

    private static TableEnvironment init() {
        try {
            return FLINK.submit(Lakehouse::batch).get();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private interface Body {
        String get(HttpExchange ex) throws Exception;
    }

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(System.getProperty("port", "20780"));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        route(server, "/api/revenue", "application/json", UiServer::revenue);
        route(server, "/api/summary", "application/json", ex -> summary());
        route(server, "/api/snapshots", "application/json", ex -> snapshots());
        route(server, "/", "text/html", ex -> page());
        server.start();
        System.out.println("ui listening on " + port);
    }

    private static String revenue(HttpExchange ex) throws Exception {
        String snapshot = param(ex, "snapshot");
        String hint = snapshot == null ? "" : " /*+ OPTIONS('scan.snapshot-id' = '" + Long.parseLong(snapshot) + "') */";
        List<Row> rows = run("SELECT category, orders, units, revenue FROM revenue_by_category" + hint + " ORDER BY category");
        return array(rows, row -> "{\"category\":" + str(row.getField(0)) + ",\"orders\":" + row.getField(1)
                + ",\"units\":" + row.getField(2) + ",\"revenue\":" + row.getField(3) + "}");
    }

    private static String summary() throws Exception {
        Row row = run("SELECT COUNT(*), COALESCE(SUM(quantity), 0), COALESCE(SUM(CAST(quantity * price AS DECIMAL(14, 2))), 0) FROM orders").getFirst();
        return "{\"orders\":" + row.getField(0) + ",\"units\":" + row.getField(1) + ",\"revenue\":" + row.getField(2) + "}";
    }

    private static String snapshots() throws Exception {
        List<Row> rows = run("SELECT snapshot_id, commit_kind, CAST(commit_time AS STRING), delta_record_count FROM `revenue_by_category$snapshots` WHERE delta_record_count > 0 ORDER BY snapshot_id DESC");
        return array(rows, row -> "{\"id\":" + row.getField(0) + ",\"kind\":" + str(row.getField(1))
                + ",\"time\":" + str(row.getField(2)) + ",\"delta\":" + row.getField(3) + "}");
    }

    private static List<Row> run(String sql) throws Exception {
        try {
            return FLINK.submit(() -> SqlConsole.query(ENV, sql)).get();
        } catch (ExecutionException e) {
            throw e.getCause() instanceof Exception cause ? cause : e;
        }
    }

    private static String array(List<Row> rows, Function<Row, String> mapper) {
        StringJoiner json = new StringJoiner(",", "[", "]");
        rows.forEach(row -> json.add(mapper.apply(row)));
        return json.toString();
    }

    private static String str(Object value) {
        return "\"" + String.valueOf(value).replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static String param(HttpExchange ex, String name) {
        String query = ex.getRequestURI().getQuery();
        if (query == null) {
            return null;
        }
        for (String pair : query.split("&")) {
            String[] kv = pair.split("=", 2);
            if (kv.length == 2 && kv[0].equals(name) && !kv[1].isBlank()) {
                return kv[1];
            }
        }
        return null;
    }

    private static String page() throws IOException {
        try (InputStream in = UiServer.class.getResourceAsStream("/index.html")) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static void route(HttpServer server, String path, String type, Body body) {
        server.createContext(path, ex -> {
            int status = 200;
            String contentType = type;
            String text;
            try {
                text = body.get(ex);
            } catch (Exception e) {
                status = 500;
                contentType = "application/json";
                text = "{\"error\":" + str(e.getMessage()) + "}";
            }
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().set("Content-Type", contentType + "; charset=utf-8");
            ex.sendResponseHeaders(status, bytes.length);
            ex.getResponseBody().write(bytes);
            ex.close();
        });
    }
}
