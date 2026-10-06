package bench;

import java.nio.file.Path;

public final class Settings {

    public static final String HOST = env("DB_HOST", "localhost");
    public static final int SCYLLA_PORT = Integer.parseInt(env("SCYLLA_PORT", "24742"));
    public static final int CASSANDRA_PORT = Integer.parseInt(env("CASSANDRA_PORT", "24743"));
    public static final int UI_PORT = Integer.parseInt(env("UI_PORT", "24780"));
    public static final int ROWS = Integer.parseInt(env("BENCH_ROWS", "100000"));
    public static final int READS = Integer.parseInt(env("BENCH_READS", "100000"));
    public static final int AGG_ROUNDS = Integer.parseInt(env("BENCH_AGG_ROUNDS", "50"));
    public static final int CONCURRENCY = Integer.parseInt(env("BENCH_CONCURRENCY", "64"));
    public static final int AGG_CONCURRENCY = Integer.parseInt(env("BENCH_AGG_CONCURRENCY", "4"));
    public static final Path BASE_CSV = Path.of(env("BASE_CSV", "data/orders.csv"));
    public static final Path BENCH_CSV = Path.of(env("BENCH_CSV", "data/bench-orders.csv"));
    public static final Path RESULTS = Path.of(env("RESULTS_FILE", "results.json"));

    private Settings() {
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
