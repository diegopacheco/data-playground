package bench;

import java.nio.file.Path;

public final class Settings {

    public static final String PD_ADDRESS = env("PD_ADDRESS", "s6-pd:2379");
    public static final String SCYLLA_HOST = env("SCYLLA_HOST", "s6-scylla");
    public static final String FDB_HOST = env("FDB_HOST", "s6-foundationdb");
    public static final int UI_PORT = Integer.parseInt(env("UI_PORT", "8080"));
    public static final Path DATASET = Path.of(env("DATASET_FILE", "data/dataset.csv"));
    public static final Path RESULTS = Path.of(env("RESULTS_FILE", "results.json"));
    public static final String LIMITS = env("STORE_LIMITS", "unknown");
    public static final int CONCURRENCY = Integer.parseInt(env("BENCH_CONCURRENCY", "16"));
    public static final int ROUNDS = Integer.parseInt(env("BENCH_ROUNDS", "3"));
    public static final int POINT_READS = Integer.parseInt(env("BENCH_POINT_READS", "30000"));
    public static final int RANGE_SCANS = Integer.parseInt(env("BENCH_RANGE_SCANS", "3000"));
    public static final int RANGE_LENGTH = Integer.parseInt(env("BENCH_RANGE_LENGTH", "100"));
    public static final int WARMUP_POINT = Integer.parseInt(env("BENCH_WARMUP_POINT", "5000"));
    public static final int WARMUP_SCAN = Integer.parseInt(env("BENCH_WARMUP_SCAN", "500"));
    public static final int LOAD_BATCH = 100;
    public static final int SAMPLE_KEYS = 1000;
    public static final int SAMPLE_RANGES = 200;
    public static final int SCAN_PAGE = 1000;
    public static final int SCYLLA_BUCKET_ROWS = 1000;

    private Settings() {
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
