import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public class Server {

    static final Path RESULTS = Path.of(env("RESULTS_DIR", "/results"));
    static final Path CSV = Path.of(env("ORDERS_CSV", "/data/orders.csv"));
    static final Path INDEX = Path.of(env("INDEX_HTML", "/app/index.html"));
    static final List<String> FORMATS = List.of("hudi", "delta", "iceberg");

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(env("PORT", "20800"));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/api/readers", ex -> json(ex, Server::readers));
        server.createContext("/api/expected", ex -> json(ex, Server::expected));
        server.createContext("/api/files", ex -> json(ex, Server::files));
        server.createContext("/", Server::index);
        server.start();
        System.out.println("ui listening on " + port);
    }

    static String env(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }

    static void index(HttpExchange ex) throws IOException {
        send(ex, 200, "text/html; charset=utf-8", Files.readAllBytes(INDEX));
    }

    static void json(HttpExchange ex, Supplier<String> body) throws IOException {
        try {
            send(ex, 200, "application/json", body.get().getBytes(StandardCharsets.UTF_8));
        } catch (RuntimeException e) {
            send(ex, 500, "application/json", ("{\"error\":" + q(String.valueOf(e.getMessage())) + "}").getBytes(StandardCharsets.UTF_8));
        }
    }

    static void send(HttpExchange ex, int status, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(status, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }

    static List<String[]> tsv(String name) {
        try {
            return Files.readAllLines(RESULTS.resolve(name)).stream()
                    .filter(line -> !line.isBlank())
                    .map(line -> line.split("\t"))
                    .toList();
        } catch (IOException e) {
            throw new IllegalStateException("missing " + name + ", run scripts/start-all.sh");
        }
    }

    static String readers() {
        Map<String, String[]> summary = tsv("readers.tsv").stream().collect(Collectors.toMap(r -> r[0], r -> r));
        List<String> items = new ArrayList<>();
        for (String format : FORMATS) {
            String[] s = summary.get(format);
            String aggregates = tsv("agg_" + format + ".tsv").stream().map(Server::aggregate).collect(Collectors.joining(","));
            String files = tsv("datafiles_" + format + ".txt").stream().map(r -> q(r[0])).collect(Collectors.joining(","));
            items.add("{\"format\":" + q(format) + ",\"rows\":" + s[1] + ",\"files\":" + s[2] + ",\"millis\":" + s[3]
                    + ",\"aggregates\":[" + aggregates + "],\"dataFiles\":[" + files + "]}");
        }
        return "{\"readers\":[" + String.join(",", items) + "]}";
    }

    static String aggregate(String[] r) {
        return "{\"category\":" + q(r[0]) + ",\"orders\":" + r[1] + ",\"units\":" + r[2] + ",\"revenue\":" + q(r[3]) + "}";
    }

    static String expected() {
        Map<String, String[]> totals = new TreeMap<>();
        try {
            List<String> lines = Files.readAllLines(CSV);
            for (String line : lines.subList(1, lines.size())) {
                if (line.isBlank()) {
                    continue;
                }
                String[] c = line.split(",");
                String[] t = totals.computeIfAbsent(c[3], k -> new String[] {k, "0", "0", "0.00"});
                int quantity = Integer.parseInt(c[4]);
                t[1] = String.valueOf(Long.parseLong(t[1]) + 1);
                t[2] = String.valueOf(Long.parseLong(t[2]) + quantity);
                t[3] = new BigDecimal(t[3]).add(new BigDecimal(c[5]).multiply(BigDecimal.valueOf(quantity))).toPlainString();
            }
        } catch (IOException e) {
            throw new IllegalStateException("cannot read " + CSV);
        }
        return "{\"aggregates\":[" + totals.values().stream().map(Server::aggregate).collect(Collectors.joining(",")) + "]}";
    }

    static String files() {
        List<String[]> before = tsv("files_before.tsv");
        List<String[]> after = tsv("files_after.tsv");
        Map<String, String> beforeHash = before.stream().collect(Collectors.toMap(r -> r[0], r -> r[1] + ":" + r[2]));
        Set<String> afterPaths = after.stream().map(r -> r[0]).collect(Collectors.toSet());
        List<String[]> added = after.stream().filter(r -> !beforeHash.containsKey(r[0])).toList();
        long changed = after.stream().filter(r -> beforeHash.containsKey(r[0]) && !beforeHash.get(r[0]).equals(r[1] + ":" + r[2])).count();
        long removed = beforeHash.keySet().stream().filter(p -> !afterPaths.contains(p)).count();
        return "{\"before\":" + dirs(before) + ",\"after\":" + dirs(after)
                + ",\"added\":[" + added.stream().map(Server::file).collect(Collectors.joining(",")) + "]"
                + ",\"changed\":" + changed + ",\"removed\":" + removed
                + ",\"beforeCount\":" + before.size() + ",\"afterCount\":" + after.size() + "}";
    }

    static String file(String[] r) {
        return "{\"path\":" + q(r[0]) + ",\"size\":" + r[1] + ",\"sha256\":" + q(r[2]) + "}";
    }

    static String dirs(List<String[]> files) {
        Map<String, long[]> groups = new LinkedHashMap<>();
        files.stream().sorted((a, b) -> a[0].compareTo(b[0])).forEach(r -> {
            long[] g = groups.computeIfAbsent(top(r[0]), k -> new long[2]);
            g[0]++;
            g[1] += Long.parseLong(r[1]);
        });
        return "[" + groups.entrySet().stream()
                .map(e -> "{\"dir\":" + q(e.getKey()) + ",\"kind\":" + q(kind(e.getKey())) + ",\"files\":" + e.getValue()[0] + ",\"bytes\":" + e.getValue()[1] + "}")
                .collect(Collectors.joining(",")) + "]";
    }

    static String top(String path) {
        int slash = path.indexOf('/');
        return slash < 0 ? path : path.substring(0, slash);
    }

    static String kind(String dir) {
        return switch (dir) {
            case ".hoodie" -> "hudi metadata";
            case "_delta_log" -> "delta metadata";
            case "metadata" -> "iceberg metadata";
            default -> "data";
        };
    }

    static String q(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
