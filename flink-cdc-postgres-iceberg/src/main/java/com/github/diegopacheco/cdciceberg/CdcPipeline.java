package com.github.diegopacheco.cdciceberg;

import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;

public class CdcPipeline {

    public static void main(String[] args) throws Exception {
        Settings settings = Settings.fromEnv();
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment(Settings.flinkPorts("PIPELINE"));
        env.setParallelism(1);
        env.enableCheckpointing(3000);
        StreamTableEnvironment tables = StreamTableEnvironment.create(env);

        tables.executeSql("CREATE TABLE pg_orders ("
                + "order_id INT NOT NULL,"
                + "customer STRING,"
                + "product STRING,"
                + "category STRING,"
                + "quantity INT,"
                + "price DECIMAL(10,2),"
                + "ts TIMESTAMP(6),"
                + "PRIMARY KEY (order_id) NOT ENFORCED"
                + ") WITH ("
                + "'connector'='postgres-cdc',"
                + "'hostname'='" + settings.pgHost() + "',"
                + "'port'='" + settings.pgPort() + "',"
                + "'username'='" + settings.pgUser() + "',"
                + "'password'='" + settings.pgPassword() + "',"
                + "'database-name'='" + settings.pgDatabase() + "',"
                + "'schema-name'='public',"
                + "'table-name'='orders',"
                + "'slot.name'='i18_orders_slot',"
                + "'decoding.plugin.name'='pgoutput',"
                + "'scan.incremental.snapshot.enabled'='true')");

        Lakehouse.registerCatalog(tables, settings);
        Lakehouse.createTable(tables);

        tables.executeSql("INSERT INTO " + Lakehouse.TABLE + " SELECT * FROM pg_orders").await();
    }
}
