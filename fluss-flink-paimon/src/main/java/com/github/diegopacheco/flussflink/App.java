package com.github.diegopacheco.flussflink;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.apache.flink.types.Row;
import org.apache.fluss.client.metadata.LakeSnapshot;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class App {

    private static final List<String> FILES = List.of("orders.csv", "orders-updates.csv");

    private final Tiering tiering = new Tiering();
    private Fluss fluss;
    private Lake lake;

    private interface Body {
        String get(HttpExchange ex) throws Exception;
    }

    public static void main(String[] args) throws Exception {
        new App().start();
    }

    private void start() throws Exception {
        fluss = Fluss.connect(60);
        tiering.start();
        HttpServer server = HttpServer.create(new InetSocketAddress(Settings.UI_PORT), 0);
        server.setExecutor(Executors.newSingleThreadExecutor());
        route(server, "GET", "/api/status", "application/json", ex -> status());
        route(server, "GET", "/api/lookup", "application/json", this::lookup);
        route(server, "GET", "/api/fluss", "application/json", ex -> flussState());
        route(server, "GET", "/api/lake", "application/json", ex -> lakeState());
        route(server, "GET", "/api/union", "application/json", ex -> unionState());
        route(server, "POST", "/api/ingest", "application/json", this::ingest);
        route(server, "POST", "/api/tiering/pause", "application/json", ex -> pause());
        route(server, "POST", "/api/tiering/resume", "application/json", ex -> resume());
        route(server, "POST", "/api/reset", "application/json", ex -> reset());
        route(server, "GET", "/", "text/html", ex -> page());
        server.start();
        System.out.println("ui listening on " + Settings.UI_PORT + ", flink web ui on " + Settings.FLINK_PORT);
    }

    private Lake lake() {
        if (lake == null) {
            lake = new Lake();
        }
        return lake;
    }

    private String status() throws Exception {
        Optional<LakeSnapshot> snapshot = fluss.lakeSnapshot();
        String lakeSnapshot = snapshot.map(s -> "{\"id\":" + s.getSnapshotId() + ",\"offsets\":"
                + Json.array(s.getTableBucketsOffset().entrySet(), e -> "{\"bucket\":" + e.getKey().getBucket() + ",\"offset\":" + e.getValue() + "}")
                + "}").orElse("null");
        return "{\"table\":" + Json.str(Fluss.ORDERS.toString()) + ",\"bootstrap\":" + Json.str(Settings.BOOTSTRAP)
                + ",\"warehouse\":" + Json.str(Settings.WAREHOUSE) + ",\"freshness\":" + Json.str(Settings.FRESHNESS)
                + ",\"tiering\":{\"running\":" + tiering.running() + ",\"status\":" + Json.str(tiering.status())
                + ",\"jobId\":" + Json.str(tiering.jobId()) + "},\"lakeSnapshot\":" + lakeSnapshot
                + ",\"flinkUi\":" + Json.str(Settings.FLINK_UI_URL) + ",\"files\":" + Json.array(FILES, Json::str) + "}";
    }

    private String lookup(HttpExchange ex) throws Exception {
        int id = parseId(param(ex, "id"));
        long start = System.nanoTime();
        Optional<Order> live = fluss.lookup(id);
        double flussMs = millis(start);
        start = System.nanoTime();
        List<Order> tiered = lake().lakeLookup(id);
        double lakeMs = millis(start);
        return "{\"id\":" + id + ",\"fluss\":" + live.map(Order::toJson).orElse("null") + ",\"fluss_ms\":" + flussMs
                + ",\"lake\":" + (tiered.isEmpty() ? "null" : tiered.getFirst().toJson()) + ",\"lake_ms\":" + lakeMs + "}";
    }

    private String flussState() throws Exception {
        long start = System.nanoTime();
        List<Order> rows = fluss.scan();
        return "{\"source\":\"fluss kv\",\"ms\":" + millis(start) + ",\"totals\":" + Json.totals(rows)
                + ",\"categories\":" + Json.categories(rows) + "}";
    }

    private String lakeState() throws Exception {
        long start = System.nanoTime();
        List<Order> rows = lake().lake();
        double ms = millis(start);
        List<Row> snapshots = lake().snapshots();
        return "{\"source\":\"paimon\",\"ms\":" + ms + ",\"totals\":" + Json.totals(rows) + ",\"categories\":" + Json.categories(rows)
                + ",\"snapshots\":" + Json.array(snapshots, r -> "{\"id\":" + r.getField(0) + ",\"kind\":" + Json.str(r.getField(1))
                + ",\"time\":" + Json.str(r.getField(2)) + ",\"total\":" + r.getField(3) + ",\"delta\":" + r.getField(4) + "}") + "}";
    }

    private String unionState() throws Exception {
        long start = System.nanoTime();
        List<Order> union = lake().union();
        double ms = millis(start);
        List<Order> tiered = lake().lake();
        Map<Integer, Order> byId = tiered.stream().collect(Collectors.toMap(Order::id, Function.identity()));
        List<Order> fresh = union.stream().filter(o -> !o.equals(byId.get(o.id()))).toList();
        return "{\"source\":\"union\",\"ms\":" + ms + ",\"totals\":" + Json.totals(union) + ",\"categories\":" + Json.categories(union)
                + ",\"lake\":{\"totals\":" + Json.totals(tiered) + ",\"categories\":" + Json.categories(tiered) + "}"
                + ",\"fresh\":" + Json.array(fresh, o -> "{\"order\":" + o.toJson() + ",\"lake\":"
                + (byId.containsKey(o.id()) ? byId.get(o.id()).toJson() : "null") + "}") + "}";
    }

    private String ingest(HttpExchange ex) throws Exception {
        String file = param(ex, "file");
        if (!FILES.contains(file)) {
            throw new IllegalArgumentException("file must be one of " + FILES);
        }
        List<Order> orders = Files.readAllLines(Path.of(Settings.DATA_DIR, file)).stream()
                .skip(1).filter(line -> !line.isBlank()).map(Order::fromCsv).toList();
        long start = System.nanoTime();
        int count = fluss.upsert(orders);
        return "{\"file\":" + Json.str(file) + ",\"rows\":" + count + ",\"ms\":" + millis(start) + "}";
    }

    private String pause() throws Exception {
        tiering.stop();
        return status();
    }

    private String resume() throws Exception {
        tiering.start();
        return status();
    }

    private String reset() throws Exception {
        tiering.stop();
        fluss.dropTable();
        lake().dropLakeTable();
        fluss.ensureTable();
        tiering.start();
        return status();
    }

    private static int parseId(String id) {
        try {
            return Integer.parseInt(id);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("id must be an integer order_id");
        }
    }

    private static double millis(long start) {
        return Math.round((System.nanoTime() - start) / 10_000.0) / 100.0;
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
        try (InputStream in = App.class.getResourceAsStream("/index.html")) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static void route(HttpServer server, String method, String path, String type, Body body) {
        server.createContext(path, ex -> {
            int status = 200;
            String contentType = type;
            String text;
            try {
                if (!ex.getRequestMethod().equals(method)) {
                    status = 405;
                    contentType = "application/json";
                    text = "{\"error\":\"use " + method + "\"}";
                } else {
                    text = body.get(ex);
                }
            } catch (IllegalArgumentException e) {
                status = 400;
                contentType = "application/json";
                text = "{\"error\":" + Json.str(e.getMessage()) + "}";
            } catch (Exception e) {
                e.printStackTrace();
                status = 500;
                contentType = "application/json";
                text = "{\"error\":" + Json.str(String.valueOf(e.getMessage())) + "}";
            }
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().set("Content-Type", contentType + "; charset=utf-8");
            ex.sendResponseHeaders(status, bytes.length);
            ex.getResponseBody().write(bytes);
            ex.close();
        });
    }
}
