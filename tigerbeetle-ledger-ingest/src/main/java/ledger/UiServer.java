package ledger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

public final class UiServer {

    private interface Body {
        String get() throws Exception;
    }

    private UiServer() {
    }

    public static void main(String[] args) throws Exception {
        List<Orders.Order> orders = Orders.load(Settings.ORDERS_CSV);
        Ledger ledger = Ledger.connect();
        byte[] html;
        try (InputStream in = UiServer.class.getResourceAsStream("/index.html")) {
            html = in.readAllBytes();
        }
        HttpServer server = HttpServer.create(new InetSocketAddress(Settings.UI_PORT), 0);
        server.createContext("/api/categories", ex -> json(ex, () -> accounts(ledger, Orders.categories(orders), Chart::category,
                name -> orders.stream().filter(o -> o.category().equals(name)).count(), "category", "credits_cents", true)));
        server.createContext("/api/customers", ex -> json(ex, () -> accounts(ledger, Orders.customers(orders), Chart::customer,
                name -> orders.stream().filter(o -> o.customer().equals(name)).count(), "customer", "debits_cents", false)));
        server.createContext("/api/bench", ex -> json(ex, () -> file("bench.json")));
        server.createContext("/api/ingest", ex -> json(ex, () -> file("ingest.json")));
        server.createContext("/", ex -> send(ex, 200, "text/html; charset=utf-8", html));
        server.start();
        System.out.println("ui listening on http://localhost:" + Settings.UI_PORT);
    }

    private static String accounts(Ledger ledger, List<String> names, Function<String, Long> idOf,
                                   Function<String, Long> orderCount, String label, String field, boolean credits) throws Exception {
        Map<Long, Ledger.Balance> balances = ledger.lookup(names.stream().map(idOf).toList());
        List<String> rows = names.stream().map(name -> {
            Ledger.Balance b = balances.get(idOf.apply(name));
            long cents = b == null ? 0 : credits ? b.creditsPosted() : b.debitsPosted();
            return String.format("{\"%s\":\"%s\",\"account_id\":\"%d\",\"orders\":%d,\"%s\":%d}",
                    label, name, idOf.apply(name), orderCount.apply(name), field, cents);
        }).toList();
        return "[" + String.join(",", rows) + "]";
    }

    private static String file(String name) throws IOException {
        Path path = Settings.RUN_DIR.resolve(name);
        return Files.exists(path) ? Files.readString(path) : "null";
    }

    private static void json(HttpExchange ex, Body body) throws IOException {
        try {
            send(ex, 200, "application/json", body.get().getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            send(ex, 500, "application/json", ("{\"error\":\"" + e.getClass().getSimpleName() + "\"}").getBytes(StandardCharsets.UTF_8));
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
