package sales;

public final class Settings {

    public static final String KAFKA_BOOTSTRAP = env("KAFKA_BOOTSTRAP", "localhost:21992");
    public static final String TOPIC = env("CDC_TOPIC", "i19.sales.orders");
    public static final String GROUP_ID = env("CDC_GROUP", "i19-cdc-cassandra");
    public static final String CASSANDRA_HOST = env("CASSANDRA_HOST", "localhost");
    public static final int CASSANDRA_PORT = Integer.parseInt(env("CASSANDRA_PORT", "21942"));
    public static final String MYSQL_URL = env("MYSQL_URL", "jdbc:mysql://localhost:21906/sales?user=app&password=app&allowPublicKeyRetrieval=true&useSSL=false");
    public static final int UI_PORT = Integer.parseInt(env("UI_PORT", "21980"));

    private Settings() {
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
