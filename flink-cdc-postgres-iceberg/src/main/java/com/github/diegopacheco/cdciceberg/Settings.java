package com.github.diegopacheco.cdciceberg;

import org.apache.flink.configuration.Configuration;

import java.nio.file.Path;

public record Settings(String pgHost, int pgPort, String pgDatabase, String pgUser, String pgPassword, Path warehouse, Path sqlDir, int uiPort) {

    public static Settings fromEnv() {
        var env = System.getenv();
        Path root = Path.of(env.getOrDefault("APP_ROOT", ".")).toAbsolutePath().normalize();
        return new Settings(
                env.getOrDefault("PG_HOST", "localhost"),
                Integer.parseInt(env.getOrDefault("PG_PORT", "21832")),
                env.getOrDefault("PG_DATABASE", "shop"),
                env.getOrDefault("PG_USER", "cdc"),
                env.getOrDefault("PG_PASSWORD", "cdc"),
                root.resolve("warehouse"),
                root.resolve("sql"),
                Integer.parseInt(env.getOrDefault("UI_PORT", "21880")));
    }

    public static Configuration flinkPorts(String role) {
        Configuration conf = new Configuration();
        conf.setString("blob.server.port", System.getenv("FLINK_" + role + "_BLOB_PORT"));
        conf.setString("taskmanager.data.port", System.getenv("FLINK_" + role + "_DATA_PORT"));
        conf.setString("rest.port", System.getenv("FLINK_" + role + "_REST_PORT"));
        return conf;
    }

    public String jdbcUrl() {
        return "jdbc:postgresql://" + pgHost + ":" + pgPort + "/" + pgDatabase;
    }
}
