package sales;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class UiServer {

    public static void main(String[] args) throws IOException {
        CqlSession session = Cassandra.connect();
        byte[] html;
        try (InputStream in = UiServer.class.getResourceAsStream("/index.html")) {
            html = in.readAllBytes();
        }
        HttpServer server = HttpServer.create(new InetSocketAddress(Settings.UI_PORT), 0);
        server.createContext("/api/revenue", ex -> send(ex, "application/json", revenueJson(session).getBytes(StandardCharsets.UTF_8)));
        server.createContext("/", ex -> send(ex, "text/html; charset=utf-8", html));
        server.start();
        System.out.println("ui listening on http://localhost:" + Settings.UI_PORT);
    }

    private static String revenueJson(CqlSession session) {
        List<Row> rows = new ArrayList<>(session.execute(
                "SELECT category, total_orders, total_quantity, total_revenue FROM sales.revenue_by_category").all());
        rows.sort(Comparator.comparingDouble((Row r) -> r.getDouble("total_revenue")).reversed());
        List<String> items = rows.stream()
                .map(r -> String.format(Locale.ROOT,
                        "{\"category\":\"%s\",\"total_orders\":%d,\"total_quantity\":%d,\"total_revenue\":%.2f}",
                        r.getString("category"), r.getLong("total_orders"), r.getLong("total_quantity"), r.getDouble("total_revenue")))
                .toList();
        return "[" + String.join(",", items) + "]";
    }

    private static void send(HttpExchange ex, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(200, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }
}
