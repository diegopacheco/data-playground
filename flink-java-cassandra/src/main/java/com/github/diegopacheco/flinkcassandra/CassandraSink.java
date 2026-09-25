package com.github.diegopacheco.flinkcassandra;

import org.apache.flink.api.connector.sink2.Sink;
import org.apache.flink.api.connector.sink2.SinkWriter;
import org.apache.flink.api.connector.sink2.WriterInitContext;

public class CassandraSink implements Sink<CategoryStats> {

    @Override
    public SinkWriter<CategoryStats> createWriter(WriterInitContext context) {
        CassandraStore store = new CassandraStore();
        return new SinkWriter<>() {
            @Override
            public void write(CategoryStats element, Context ctx) {
                store.save(element);
            }

            @Override
            public void flush(boolean endOfInput) {
            }

            @Override
            public void close() {
                store.close();
            }
        };
    }
}
