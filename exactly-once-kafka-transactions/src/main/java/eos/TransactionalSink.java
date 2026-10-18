package eos;

import java.time.Duration;
import java.util.Map;
import java.util.Properties;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;

final class TransactionalSink implements Sink {
    private final KafkaProducer<String, String> producer;
    private final KafkaConsumer<String, String> consumer;

    TransactionalSink(String transactionalId, KafkaConsumer<String, String> consumer) {
        Properties p = Settings.producer();
        p.put("transactional.id", transactionalId);
        this.producer = new KafkaProducer<>(p);
        this.consumer = consumer;
        producer.initTransactions();
    }

    public void begin() {
        producer.beginTransaction();
    }

    public void send(ProducerRecord<String, String> record) {
        producer.send(record);
    }

    public void flush() {
        producer.flush();
    }

    public void commit(Map<TopicPartition, OffsetAndMetadata> offsets) {
        producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
        producer.commitTransaction();
    }

    public void close() {
        producer.close(Duration.ofSeconds(5));
    }
}
