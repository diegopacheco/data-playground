package events;

import static org.apache.spark.sql.functions.col;
import static org.apache.spark.sql.functions.from_json;
import static org.apache.spark.sql.functions.timestamp_millis;

import org.apache.spark.sql.Dataset;
import org.apache.spark.sql.Row;
import org.apache.spark.sql.SparkSession;
import org.apache.spark.sql.types.DataTypes;
import org.apache.spark.sql.types.StructType;

public final class KafkaEvents {

    public static final StructType PAYLOAD = new StructType()
            .add("id", DataTypes.StringType)
            .add("seq", DataTypes.LongType)
            .add("event_time_ms", DataTypes.LongType);

    private KafkaEvents() {
    }

    public static Dataset<Row> read(SparkSession spark, JobArgs args) {
        return spark.readStream()
                .format("kafka")
                .option("kafka.bootstrap.servers", args.bootstrap())
                .option("subscribe", args.topic())
                .option("startingOffsets", args.startingOffsets())
                .option("failOnDataLoss", "true")
                .load();
    }

    public static Dataset<Row> parse(Dataset<Row> kafkaRows) {
        Dataset<Row> decoded = kafkaRows.select(
                from_json(col("value").cast(DataTypes.StringType), PAYLOAD).as("e"),
                col("partition"),
                col("offset"));
        return decoded.select(
                col("e.id").as("id"),
                col("e.seq").as("seq"),
                timestamp_millis(col("e.event_time_ms")).as("event_time"),
                col("partition").as("kafka_partition"),
                col("offset").as("kafka_offset"));
    }
}
