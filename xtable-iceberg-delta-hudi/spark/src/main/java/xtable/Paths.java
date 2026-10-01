package xtable;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

final class Paths {

    static final String TABLE = env("TABLE_PATH", "/lake/orders");
    static final String CSV = env("ORDERS_CSV", "/data/orders.csv");
    static final Path RESULTS = Path.of(env("RESULTS_DIR", "/results"));

    private Paths() {
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }

    static void write(String name, List<String> lines) throws IOException {
        Files.createDirectories(RESULTS);
        Files.write(RESULTS.resolve(name), lines);
    }

    static String relative(String file) {
        int at = file.indexOf(TABLE + "/");
        return at < 0 ? file : file.substring(at + TABLE.length() + 1);
    }
}
