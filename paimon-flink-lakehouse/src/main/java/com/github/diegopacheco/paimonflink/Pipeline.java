package com.github.diegopacheco.paimonflink;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.StatementSet;
import org.apache.flink.table.api.TableEnvironment;

public final class Pipeline {

    public static void main(String[] args) throws Exception {
        TableEnvironment env = TableEnvironment.create(EnvironmentSettings.inStreamingMode());
        env.getConfig().set("parallelism.default", "1");
        env.getConfig().set("execution.checkpointing.interval", "3 s");
        env.getConfig().set("table.exec.sink.upsert-materialize", "NONE");
        env.getConfig().set("pipeline.name", "i7-paimon-pipeline");
        Lakehouse.open(env);
        env.executeSql(kafkaSource(System.getProperty("bootstrap", "localhost:20792"), System.getProperty("topic", "i7-orders")));
        StatementSet statements = env.createStatementSet();
        statements.addInsertSql("""
                INSERT INTO orders
                SELECT order_id, customer, product, category, quantity, price, ts FROM kafka_orders""");
        statements.addInsertSql("""
                INSERT INTO revenue_by_category
                SELECT category, CAST(1 AS BIGINT), CAST(quantity AS BIGINT), CAST(quantity * price AS DECIMAL(14, 2))
                FROM orders /*+ OPTIONS('consumer-id' = 'i7-revenue') */""");
        statements.execute().await();
    }

    private static String kafkaSource(String bootstrap, String topic) {
        return """
                CREATE TEMPORARY TABLE kafka_orders (
                  order_id INT,
                  customer STRING,
                  product STRING,
                  category STRING,
                  quantity INT,
                  price DECIMAL(10, 2),
                  ts STRING
                ) WITH (
                  'connector' = 'kafka',
                  'topic' = '%s',
                  'properties.bootstrap.servers' = '%s',
                  'properties.group.id' = 'i7-paimon-pipeline',
                  'properties.auto.offset.reset' = 'earliest',
                  'scan.startup.mode' = 'group-offsets',
                  'format' = 'csv'
                )""".formatted(topic, bootstrap);
    }
}
