package bench;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.IntStream;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.ByteArrayDeserializer;
import org.apache.kafka.common.serialization.ByteArraySerializer;

public final class KafkaBench implements BrokerBench {

    static final Map<String, String> TOPIC_CONFIGS = Map.of(
            "message.timestamp.type", "LogAppendTime",
            "min.insync.replicas", "1");

    @Override
    public Outcome run(BenchConfig cfg) throws Exception {
        createTopic(cfg);
        Recorder recorder = new Recorder(cfg.partitions(), Long.MAX_VALUE, 1000);
        AtomicBoolean stop = new AtomicBoolean();
        CountDownLatch ready = new CountDownLatch(1);
        Thread consumer = Thread.ofVirtual().start(() -> consume(cfg, recorder, ready, stop));
        if (!ready.await(30, TimeUnit.SECONDS)) {
            throw new IllegalStateException("kafka consumer did not get ready in 30s");
        }
        recorder.warmupUntil(Payload.nowUs() + cfg.warmupMicros());
        ProducerOutcome producer = produce(cfg);
        BrokerBench.drain(recorder, producer.sent(), cfg.drainSeconds());
        stop.set(true);
        consumer.join();
        return new Outcome(producer, recorder);
    }

    private static void createTopic(BenchConfig cfg) throws Exception {
        Properties props = new Properties();
        props.put("bootstrap.servers", cfg.address());
        try (Admin admin = Admin.create(props)) {
            NewTopic topic = new NewTopic(cfg.topic(), cfg.partitions(), (short) 1).configs(TOPIC_CONFIGS);
            admin.createTopics(List.of(topic)).all().get(30, TimeUnit.SECONDS);
        }
    }

    static Properties producerProps(String bootstrap) {
        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrap);
        props.put("acks", "all");
        props.put("linger.ms", "0");
        props.put("enable.idempotence", "true");
        props.put("key.serializer", ByteArraySerializer.class.getName());
        props.put("value.serializer", ByteArraySerializer.class.getName());
        return props;
    }

    static Properties consumerProps(String bootstrap) {
        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrap);
        props.put("enable.auto.commit", "false");
        props.put("fetch.min.bytes", "1");
        props.put("fetch.max.wait.ms", "100");
        props.put("max.partition.fetch.bytes", String.valueOf(4 * 1024 * 1024));
        props.put("key.deserializer", ByteArrayDeserializer.class.getName());
        props.put("value.deserializer", ByteArrayDeserializer.class.getName());
        return props;
    }

    private static ProducerOutcome produce(BenchConfig cfg) {
        AtomicLong errors = new AtomicLong();
        try (KafkaProducer<byte[], byte[]> producer = new KafkaProducer<>(producerProps(cfg.address()))) {
            long startedAtUs = Payload.nowUs();
            long begin = System.nanoTime();
            long sent = 0;
            double elapsed;
            while ((elapsed = (System.nanoTime() - begin) / 1e9) < cfg.seconds()) {
                int count = Pacer.due(elapsed, cfg.rate(), sent, cfg.batchCap());
                if (count == 0) {
                    BrokerBench.pause();
                    continue;
                }
                for (long seq = sent; seq < sent + count; seq++) {
                    byte[] value = Payload.encode(seq, Payload.nowUs(), cfg.size());
                    int partition = (int) (seq % cfg.partitions());
                    producer.send(new ProducerRecord<>(cfg.topic(), partition, null, value), (meta, error) -> {
                        if (error != null) {
                            errors.incrementAndGet();
                        }
                    });
                }
                sent += count;
            }
            producer.flush();
            return new ProducerOutcome(sent, errors.get(), startedAtUs, Payload.nowUs());
        }
    }

    private static void consume(BenchConfig cfg, Recorder recorder, CountDownLatch ready, AtomicBoolean stop) {
        try (KafkaConsumer<byte[], byte[]> consumer = new KafkaConsumer<>(consumerProps(cfg.address()))) {
            List<TopicPartition> partitions = IntStream.range(0, cfg.partitions())
                    .mapToObj(p -> new TopicPartition(cfg.topic(), p))
                    .toList();
            consumer.assign(partitions);
            consumer.seekToBeginning(partitions);
            partitions.forEach(consumer::position);
            ready.countDown();
            while (!stop.get()) {
                var records = consumer.poll(Duration.ofMillis(100));
                long receivedAtUs = Payload.nowUs();
                for (ConsumerRecord<byte[], byte[]> record : records) {
                    recorder.observe(record.partition(), record.value(), record.timestamp() * 1000, receivedAtUs);
                }
            }
        }
    }
}
