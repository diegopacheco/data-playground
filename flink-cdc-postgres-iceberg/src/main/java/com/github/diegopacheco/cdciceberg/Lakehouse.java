package com.github.diegopacheco.cdciceberg;

import org.apache.flink.table.api.TableEnvironment;

public final class Lakehouse {

    public static final String TABLE = "lake.shop.orders";

    private Lakehouse() {
    }

    public static void registerCatalog(TableEnvironment env, Settings settings) {
        env.executeSql("CREATE CATALOG lake WITH ("
                + "'type'='iceberg',"
                + "'catalog-type'='hadoop',"
                + "'cache-enabled'='false',"
                + "'warehouse'='" + settings.warehouse().toUri() + "')");
    }

    public static void createTable(TableEnvironment env) {
        env.executeSql("CREATE DATABASE IF NOT EXISTS lake.shop");
        env.executeSql("CREATE TABLE IF NOT EXISTS " + TABLE + " ("
                + "order_id INT NOT NULL,"
                + "customer STRING,"
                + "product STRING,"
                + "category STRING,"
                + "quantity INT,"
                + "price DECIMAL(10,2),"
                + "ts TIMESTAMP(6),"
                + "PRIMARY KEY (order_id) NOT ENFORCED"
                + ") WITH ("
                + "'format-version'='2',"
                + "'flink.max-continuous-empty-commits'='2147483647',"
                + "'write.upsert.enabled'='true')");
    }
}
