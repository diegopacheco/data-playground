package ledger;

import java.nio.file.Path;

public final class Settings {

    public static final String TB_ADDRESS = env("TB_ADDRESS", "127.0.0.1:24900");
    public static final int UI_PORT = Integer.parseInt(env("UI_PORT", "24901"));
    public static final Path ORDERS_CSV = Path.of(env("ORDERS_CSV", "data/orders.csv"));
    public static final Path RUN_DIR = Path.of(env("RUN_DIR", ".run"));
    public static final int BENCH_TRANSFERS = Integer.parseInt(env("BENCH_TRANSFERS", "1000000"));
    public static final int BENCH_ACCOUNTS = Integer.parseInt(env("BENCH_ACCOUNTS", "1000"));
    public static final int BATCH_SIZE = 8189;
    public static final int ORDERS_LEDGER = 1;
    public static final int BENCH_LEDGER = 2;
    public static final int CUSTOMER_CODE = 1;
    public static final int REVENUE_CODE = 2;
    public static final int BENCH_CODE = 3;
    public static final int ORDER_CODE = 10;
    public static final int BENCH_TRANSFER_CODE = 20;

    private Settings() {
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }
}
