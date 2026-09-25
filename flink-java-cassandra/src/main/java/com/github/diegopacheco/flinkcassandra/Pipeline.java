package com.github.diegopacheco.flinkcassandra;

import org.apache.flink.api.common.RuntimeExecutionMode;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.connector.file.src.FileSource;
import org.apache.flink.connector.file.src.reader.TextLineInputFormat;
import org.apache.flink.core.fs.Path;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;

import java.io.File;

public class Pipeline {

    public static void main(String[] args) throws Exception {
        String csv = args.length > 0 ? args[0] : "data/orders.csv";
        try (CassandraStore store = new CassandraStore()) {
            store.createSchema();
        }
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setRuntimeMode(RuntimeExecutionMode.BATCH);
        env.setParallelism(1);
        FileSource<String> source = FileSource.forRecordStreamFormat(new TextLineInputFormat(), new Path(new File(csv).getAbsolutePath())).build();
        env.fromSource(source, WatermarkStrategy.noWatermarks(), "orders-csv")
                .filter(line -> !line.isBlank() && !line.startsWith("order_id"))
                .map(CategoryStats::fromCsvLine)
                .keyBy(CategoryStats::category)
                .reduce(CategoryStats::merge)
                .sinkTo(new CassandraSink())
                .name("cassandra-revenue-by-category");
        env.execute("revenue-by-category");
    }
}
