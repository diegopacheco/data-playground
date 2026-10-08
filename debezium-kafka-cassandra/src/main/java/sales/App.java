package sales;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.Callable;
import java.util.function.Function;
import java.util.stream.Collectors;

public class App {

    private static final ObjectMapper JSON = JsonMapper.builder().build();

    public static void main(String[] args) throws IOException {
        CassandraStore cassandra = new CassandraStore();
        MySqlStore mysql = new MySqlStore();
        ChangeLog changes = new ChangeLog();
        Thread consumer = new Thread(() -> {
            try {
                new CdcConsumer(cassandra, changes).run();
            } catch (RuntimeException e) {
                e.printStackTrace();
                System.exit(1);
            }
        }, "cdc-consumer");
        consumer.start();

        byte[] html;
        try (InputStream in = App.class.getResourceAsStream("/index.html")) {
            html = in.readAllBytes();
        }
        HttpServer server = HttpServer.create(new InetSocketAddress(Settings.UI_PORT), 0);
        server.createContext("/api/compare", ex -> json(ex, () -> compare(mysql, cassandra)));
        server.createContext("/api/events", ex -> json(ex, () -> Map.of("counts", changes.counts(), "recent", changes.recent())));
        server.createContext("/api/mysql/insert", ex -> mutate(ex, mysql::insert));
        server.createContext("/api/mysql/update", ex -> mutate(ex, mysql::update));
        server.createContext("/api/mysql/delete", ex -> mutate(ex, mysql::delete));
        server.createContext("/", ex -> send(ex, 200, "text/html; charset=utf-8", html));
        server.start();
        System.out.println("ui listening on http://localhost:" + Settings.UI_PORT);
    }

    private static Map<String, Object> compare(MySqlStore mysql, CassandraStore cassandra) throws Exception {
        Map<String, Totals> left = index(mysql.totals());
        Map<String, Totals> right = index(cassandra.totals());
        TreeSet<String> names = new TreeSet<>(left.keySet());
        names.addAll(right.keySet());
        List<Map<String, Object>> rows = names.stream().map(name -> {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("category", name);
            row.put("mysql", view(left.get(name)));
            row.put("cassandra", view(right.get(name)));
            row.put("match", view(left.get(name)).equals(view(right.get(name))));
            return row;
        }).toList();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("mysqlRows", mysql.orderCount());
        result.put("cassandraRows", cassandra.orderCount());
        result.put("allMatch", rows.stream().allMatch(r -> (Boolean) r.get("match")));
        result.put("categories", rows);
        return result;
    }

    private static Map<String, Totals> index(List<Totals> totals) {
        return totals.stream().collect(Collectors.toMap(Totals::category, Function.identity(), (a, b) -> a, TreeMap::new));
    }

    private static Map<String, Object> view(Totals t) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("orders", t == null ? 0 : t.orders());
        m.put("quantity", t == null ? 0 : t.quantity());
        m.put("revenue", t == null ? "0.00" : t.revenue().toPlainString());
        return m;
    }

    private static void mutate(HttpExchange ex, Callable<String> action) throws IOException {
        if (!"POST".equals(ex.getRequestMethod())) {
            send(ex, 405, "text/plain", "POST only".getBytes(StandardCharsets.UTF_8));
            return;
        }
        json(ex, () -> Map.of("result", action.call()));
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
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }
}
