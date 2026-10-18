package eos;

import java.util.Map;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;

interface Sink extends AutoCloseable {
    void begin();

    void send(ProducerRecord<String, String> record);

    void flush();

    void commit(Map<TopicPartition, OffsetAndMetadata> offsets);

    @Override
    void close();
}
