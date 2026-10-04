package com.github.diegopacheco.temporaletl;

public final class Config {

    public static final String TASK_QUEUE = "i41-etl";

    private Config() {
    }

    public static String get(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("missing environment variable " + name);
        }
        return value;
    }

    public static String temporalAddress() {
        return get("TEMPORAL_ADDRESS");
    }

    public static String pgUrl() {
        return get("PG_URL");
    }

    public static String pgUser() {
        return get("PG_USER");
    }

    public static String pgPassword() {
        return get("PG_PASSWORD");
    }
}
