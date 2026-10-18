package eos;

import java.time.Duration;
import java.util.Map;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;

final class PlainSink implements Sink {
    private final KafkaProducer<String, String> producer = new KafkaProducer<>(Settings.producer());
    private final KafkaConsumer<String, String> consumer;

    PlainSink(KafkaConsumer<String, String> consumer) {
        this.consumer = consumer;
    }

    public void begin() {
    }

    public void send(ProducerRecord<String, String> record) {
        producer.send(record);
    }

    public void flush() {
        producer.flush();
    }

    public void commit(Map<TopicPartition, OffsetAndMetadata> offsets) {
        producer.flush();
        consumer.commitSync(offsets);
    }

    public void close() {
        producer.close(Duration.ofSeconds(5));
    }
}
