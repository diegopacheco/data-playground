package com.github.diegopacheco.paimonflink;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;

import java.nio.file.Path;

public final class Lakehouse {

    private Lakehouse() {
    }

    public static String warehouse() {
        return Path.of(System.getProperty("warehouse", "warehouse")).toAbsolutePath().toUri().toString();
    }

    public static TableEnvironment batch() {
        TableEnvironment env = TableEnvironment.create(EnvironmentSettings.inBatchMode());
        env.getConfig().set("parallelism.default", "1");
        open(env);
        return env;
    }

    public static void open(TableEnvironment env) {
        env.executeSql("CREATE CATALOG lake WITH ('type' = 'paimon', 'warehouse' = '" + warehouse() + "', 'cache-enabled' = 'false')");
        env.executeSql("USE CATALOG lake");
        env.executeSql("""
                CREATE TABLE IF NOT EXISTS orders (
                  order_id INT,
                  customer STRING,
                  product STRING,
                  category STRING,
                  quantity INT,
                  price DECIMAL(10, 2),
                  ts STRING,
                  PRIMARY KEY (order_id) NOT ENFORCED
                ) WITH (
                  'bucket' = '1',
                  'changelog-producer' = 'lookup',
                  'consumer.expiration-time' = '1 d'
                )""");
        env.executeSql("""
                CREATE TABLE IF NOT EXISTS revenue_by_category (
                  category STRING,
                  orders BIGINT,
                  units BIGINT,
                  revenue DECIMAL(14, 2),
                  PRIMARY KEY (category) NOT ENFORCED
                ) WITH (
                  'bucket' = '1',
                  'merge-engine' = 'aggregation',
                  'fields.orders.aggregate-function' = 'sum',
                  'fields.units.aggregate-function' = 'sum',
                  'fields.revenue.aggregate-function' = 'sum'
                )""");
    }
}
