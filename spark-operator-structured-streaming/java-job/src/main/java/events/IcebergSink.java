package events;

import java.util.concurrent.TimeoutException;
import org.apache.spark.sql.Dataset;
import org.apache.spark.sql.Row;
import org.apache.spark.sql.SparkSession;
import org.apache.spark.sql.streaming.StreamingQuery;
import org.apache.spark.sql.streaming.Trigger;

public final class IcebergSink {

    private IcebergSink() {
    }

    public static void createTable(SparkSession spark, String table) {
        spark.sql("CREATE TABLE IF NOT EXISTS " + table
                + " (id STRING, seq BIGINT, event_time TIMESTAMP, kafka_partition INT, kafka_offset BIGINT)"
                + " USING iceberg TBLPROPERTIES ('format-version'='2')");
    }

    public static StreamingQuery start(Dataset<Row> events, String table, String checkpoint, Trigger trigger) throws TimeoutException {
        return events.writeStream()
                .format("iceberg")
                .outputMode("append")
                .trigger(trigger)
                .option("checkpointLocation", checkpoint)
                .queryName(table)
                .toTable(table);
    }
}
