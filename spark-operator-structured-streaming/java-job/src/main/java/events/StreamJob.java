package events;

import org.apache.spark.sql.SparkSession;
import org.apache.spark.sql.streaming.StreamingQuery;
import org.apache.spark.sql.streaming.Trigger;

public final class StreamJob {

    private StreamJob() {
    }

    public static void main(String[] argv) throws Exception {
        JobArgs args = JobArgs.parse(argv);
        SparkSession spark = SparkSession.builder().appName("events-java " + args.table()).getOrCreate();
        IcebergSink.createTable(spark, args.table());
        StreamingQuery query = IcebergSink.start(
                KafkaEvents.parse(KafkaEvents.read(spark, args)),
                args.table(),
                args.checkpoint(),
                Trigger.ProcessingTime(args.triggerSeconds() * 1000));
        query.awaitTermination();
    }
}
