package sales;

public final class Settings {
    public static final String TOPIC = "orders";
    public static final String KAFKA = env("KAFKA_BOOTSTRAP", "localhost:13092");
    public static final String CASSANDRA_HOST = env("CASSANDRA_HOST", "localhost");
    public static final int CASSANDRA_PORT = Integer.parseInt(env("CASSANDRA_PORT", "13042"));
    public static final int UI_PORT = Integer.parseInt(env("UI_PORT", "13080"));
    public static final String CSV = env("ORDERS_CSV", "data/orders.csv");
    public static final String STATE_DIR = env("STREAMS_STATE_DIR", ".run/kafka-streams");

    private Settings() {
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
