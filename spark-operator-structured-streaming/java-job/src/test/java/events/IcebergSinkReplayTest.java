package events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Collectors;
import java.util.stream.LongStream;
import org.apache.spark.api.java.function.VoidFunction2;
import org.apache.spark.sql.Dataset;
import org.apache.spark.sql.Row;
import org.apache.spark.sql.SparkSession;
import org.apache.spark.sql.streaming.StreamingQuery;
import org.apache.spark.sql.streaming.Trigger;
import org.apache.spark.sql.types.DataTypes;
import org.apache.spark.sql.types.StructType;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class IcebergSinkReplayTest {

    private static final int ROWS = 50;
    private static final StructType EVENTS = new StructType()
            .add("id", DataTypes.StringType)
            .add("seq", DataTypes.LongType)
            .add("event_time", DataTypes.TimestampType)
            .add("kafka_partition", DataTypes.IntegerType)
            .add("kafka_offset", DataTypes.LongType);

    @TempDir
    static Path root;

    private static SparkSession spark;

    @BeforeAll
    static void start() throws IOException {
        spark = LocalSpark.withWarehouse(root.resolve("warehouse"));
        Path input = Files.createDirectories(root.resolve("input"));
        String lines = LongStream.range(0, ROWS)
                .mapToObj(i -> "{\"id\":\"p-" + i + "\",\"seq\":" + i + ",\"event_time\":\"2026-01-01T00:00:00Z\",\"kafka_partition\":0,\"kafka_offset\":" + i + "}")
                .collect(Collectors.joining("\n"));
        Files.writeString(input.resolve("part-0.json"), lines);
    }

    @AfterAll
    static void stop() {
        spark.stop();
    }

    @Test
    void aBatchReplayedAfterACrashBetweenIcebergCommitAndSparkCommitLogIsNotWrittenTwice() throws Exception {
        String table = "lake.db.idempotent";
        Path checkpoint = root.resolve("cp-idempotent");
        IcebergSink.createTable(spark, table);
        runOnce(IcebergSink.start(source(), table, checkpoint.toUri().toString(), Trigger.AvailableNow()));
        assertEquals(ROWS, count(table));

        simulateCrashAfterSinkCommit(checkpoint);
        runOnce(IcebergSink.start(source(), table, checkpoint.toUri().toString(), Trigger.AvailableNow()));

        assertTrue(Files.exists(checkpoint.resolve("commits/0")), "Spark replayed batch 0 and logged it again");
        assertEquals(ROWS, count(table));
        assertEquals(ROWS, distinctOffsets(table));
        assertEquals(1L, spark.sql("SELECT count(*) FROM " + table + ".snapshots").first().getLong(0));
    }

    @Test
    void aPlainAppendInForeachBatchDuplicatesTheSameReplayWhichIsWhyTheIcebergStreamingSinkIsUsed() throws Exception {
        String table = "lake.db.plain_append";
        Path checkpoint = root.resolve("cp-plain");
        IcebergSink.createTable(spark, table);
        runOnce(plainAppend(table, checkpoint));
        simulateCrashAfterSinkCommit(checkpoint);
        runOnce(plainAppend(table, checkpoint));

        assertEquals(2L * ROWS, count(table));
        assertEquals(ROWS, distinctOffsets(table));
    }

    private Dataset<Row> source() {
        return spark.readStream().schema(EVENTS).json(root.resolve("input").toString());
    }

    private StreamingQuery plainAppend(String table, Path checkpoint) throws Exception {
        VoidFunction2<Dataset<Row>, Long> append = (batch, id) -> batch.writeTo(table).append();
        return source().writeStream()
                .trigger(Trigger.AvailableNow())
                .option("checkpointLocation", checkpoint.toUri().toString())
                .foreachBatch(append)
                .start();
    }

    private static void simulateCrashAfterSinkCommit(Path checkpoint) throws IOException {
        Files.delete(checkpoint.resolve("commits/0"));
        Files.deleteIfExists(checkpoint.resolve("commits/.0.crc"));
    }

    private static void runOnce(StreamingQuery query) throws Exception {
        query.awaitTermination();
    }

    private static long count(String table) {
        return spark.table(table).count();
    }

    private static long distinctOffsets(String table) {
        return spark.table(table).select("kafka_partition", "kafka_offset").distinct().count();
    }
}
