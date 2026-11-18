package events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.util.List;
import org.apache.spark.sql.Dataset;
import org.apache.spark.sql.Row;
import org.apache.spark.sql.RowFactory;
import org.apache.spark.sql.SparkSession;
import org.apache.spark.sql.types.DataTypes;
import org.apache.spark.sql.types.StructType;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class KafkaEventsTest {

    private static final StructType KAFKA = new StructType()
            .add("value", DataTypes.BinaryType)
            .add("partition", DataTypes.IntegerType)
            .add("offset", DataTypes.LongType);

    @TempDir
    static Path warehouse;

    private static SparkSession spark;

    @BeforeAll
    static void start() {
        spark = LocalSpark.withWarehouse(warehouse);
    }

    @AfterAll
    static void stop() {
        spark.stop();
    }

    @Test
    void eventTimeComesFromThePayloadSoLatencyIsMeasuredFromWhenTheEventHappened() {
        Row row = parse("{\"id\":\"p-7\",\"seq\":7,\"event_time_ms\":1767225600123}", 1, 42L).get(0);
        assertEquals("p-7", row.getString(0));
        assertEquals(7L, row.getLong(1));
        assertEquals(1767225600123L, ((Timestamp) row.get(2)).getTime());
    }

    @Test
    void partitionAndOffsetAreKeptSoEveryRowCanBeTracedBackToExactlyOneKafkaRecord() {
        Row row = parse("{\"id\":\"p-1\",\"seq\":1,\"event_time_ms\":1}", 1, 42L).get(0);
        assertEquals(1, row.getInt(3));
        assertEquals(42L, row.getLong(4));
    }

    private List<Row> parse(String json, int partition, long offset) {
        Dataset<Row> kafka = spark.createDataFrame(
                List.of(RowFactory.create(json.getBytes(StandardCharsets.UTF_8), partition, offset)), KAFKA);
        return KafkaEvents.parse(kafka).collectAsList();
    }
}
