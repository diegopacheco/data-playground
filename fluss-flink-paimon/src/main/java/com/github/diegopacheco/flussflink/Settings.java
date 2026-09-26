package com.github.diegopacheco.flussflink;

import org.apache.flink.configuration.Configuration;

public final class Settings {

    public static final String BOOTSTRAP = env("FLUSS_BOOTSTRAP", "r1-fluss-coordinator:9123");
    public static final String WAREHOUSE = env("PAIMON_WAREHOUSE", "file:///lake/paimon");
    public static final String DATA_DIR = env("DATA_DIR", "/app/data");
    public static final String FRESHNESS = env("LAKE_FRESHNESS", "5s");
    public static final String FLINK_UI_URL = env("FLINK_UI_URL", "http://localhost:26601");
    public static final int UI_PORT = Integer.parseInt(env("UI_PORT", "8080"));
    public static final int FLINK_PORT = Integer.parseInt(env("FLINK_PORT", "8081"));
    public static final String DATABASE = "fluss";
    public static final String TABLE = "orders";

    private Settings() {
    }

    public static Configuration localCluster() {
        Configuration conf = new Configuration();
        conf.setString("parallelism.default", "1");
        conf.setString("taskmanager.memory.managed.size", "32m");
        conf.setString("taskmanager.memory.network.min", "16m");
        conf.setString("taskmanager.memory.network.max", "16m");
        return conf;
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
