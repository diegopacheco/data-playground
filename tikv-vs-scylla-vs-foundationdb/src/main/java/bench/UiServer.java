package bench;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.function.Function;
import java.util.stream.Collectors;

public class UiServer {

    private static final String KEY = "key-\\d{12}";

    private static Map<String, Store> stores;

    public static void main(String[] args) throws IOException {
        byte[] html;
        try (InputStream in = UiServer.class.getResourceAsStream("/index.html")) {
            html = in.readAllBytes();
        }
        stores = Store.openAll().stream().collect(Collectors.toMap(Store::name, Function.identity()));
        HttpServer server = HttpServer.create(new InetSocketAddress(Settings.UI_PORT), 0);
        server.setExecutor(Executors.newFixedThreadPool(8));
        server.createContext("/api/results", UiServer::results);
        server.createContext("/api/get", ex -> answer(ex, UiServer::get));
        server.createContext("/api/scan", ex -> answer(ex, UiServer::scan));
        server.createContext("/api/digest", ex -> answer(ex, UiServer::digest));
        server.createContext("/", ex -> send(ex, 200, "text/html; charset=utf-8", html));
        server.start();
        System.out.println("ui listening on port " + Settings.UI_PORT);
    }

    private static void results(HttpExchange ex) throws IOException {
        if (Files.exists(Settings.RESULTS)) {
            send(ex, 200, "application/json", Files.readAllBytes(Settings.RESULTS));
        } else {
            send(ex, 404, "text/plain", Store.bytes("results.json not found, run ./scripts/start-all.sh\n"));
        }
    }

    private static String get(Store store, Map<String, String> query) {
        byte[] value = store.get(key(query.get("key")));
        return value == null ? null : Store.text(value) + "\n";
    }

    private static String scan(Store store, Map<String, String> query) {
        int limit = Integer.parseInt(query.getOrDefault("n", "10"));
        if (limit < 1 || limit > Settings.SCAN_PAGE) throw new IllegalArgumentException("n must be between 1 and " + Settings.SCAN_PAGE);
        return Verify.lines(store.scan(key(query.get("start")), limit));
    }

    private static String digest(Store store, Map<String, String> query) {
        Verify.Digest digest = Verify.digest(store);
        return digest.sha256() + " " + digest.rows() + "\n";
    }

    private static String key(String key) {
        if (key == null || !key.matches(KEY)) throw new IllegalArgumentException("key must look like " + Verify.FIRST_KEY);
        return key;
    }

    interface Handler {
        String handle(Store store, Map<String, String> query);
    }

    private static void answer(HttpExchange ex, Handler handler) throws IOException {
        try {
            Map<String, String> query = query(ex);
            Store store = stores.get(query.get("store"));
            if (store == null) throw new IllegalArgumentException("store must be one of " + stores.keySet());
            String body = handler.handle(store, query);
            if (body == null) {
                send(ex, 404, "text/plain", Store.bytes("not found\n"));
            } else {
                send(ex, 200, "text/plain", Store.bytes(body));
            }
        } catch (IllegalArgumentException e) {
            send(ex, 400, "text/plain", Store.bytes(e.getMessage() + "\n"));
        } catch (RuntimeException e) {
            send(ex, 500, "text/plain", Store.bytes(e + "\n"));
        }
    }

    private static Map<String, String> query(HttpExchange ex) {
        Map<String, String> query = new HashMap<>();
        String raw = ex.getRequestURI().getRawQuery();
        if (raw == null) return query;
        for (String pair : raw.split("&")) {
            String[] parts = pair.split("=", 2);
            if (parts.length == 2) query.put(parts[0], URLDecoder.decode(parts[1], StandardCharsets.UTF_8));
        }
        return query;
    }

    private static void send(HttpExchange ex, int status, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(status, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }
}
