package eos;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.KafkaException;
import org.apache.kafka.common.TopicPartition;

public final class Worker {
    public static void main(String[] args) throws Exception {
        String scenario = args[0];
        boolean transactional = args[1].equals("transactional");
        long holdAt = Long.parseLong(args[2]);
        long pid = ProcessHandle.current().pid();
        TopicPartition input = new TopicPartition(Settings.in(scenario), 0);
        var settings = Settings.consumer("read_committed");
        settings.put("group.id", scenario + "-group");
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(settings);
             Sink sink = transactional ? new TransactionalSink(scenario + "-tx", consumer) : new PlainSink(consumer)) {
            consumer.assign(List.of(input));
            long end = consumer.endOffsets(List.of(input)).get(input);
            long start = consumer.position(input);
            Events.log(scenario, "worker pid " + pid + " started as " + args[1] + " at committed offset " + start);
            boolean open = false;
            while (consumer.position(input) < end) {
                for (ConsumerRecord<String, String> record : consumer.poll(Duration.ofMillis(500))) {
                    if (!open) {
                        sink.begin();
                        open = true;
                    }
                    if (record.offset() == holdAt) {
                        hold(scenario, sink, pid, holdAt);
                    }
                    sink.send(new ProducerRecord<>(Settings.out(scenario), record.key(), settle(record.value())));
                    long next = record.offset() + 1;
                    if (next % Settings.BATCH == 0 || next == end) {
                        sink.commit(Map.of(input, new OffsetAndMetadata(next)));
                        open = false;
                    }
                }
            }
            Events.log(scenario, "worker pid " + pid + " drained the input, committed offsets " + start + " to " + end);
        } catch (KafkaException e) {
            Throwable root = e;
            while (root.getCause() != null) {
                root = root.getCause();
            }
            String name = root.getClass().getSimpleName();
            Files.writeString(Settings.RUN.resolve(scenario + ".fenced"), name);
            Events.log(scenario, "worker pid " + pid + " rejected by the broker: " + name);
            System.exit(3);
        }
    }

    static String settle(String payment) {
        long cents = Long.parseLong(payment.substring(payment.indexOf(',') + 1));
        return payment + "," + cents * 3 / 100;
    }

    private static void hold(String scenario, Sink sink, long pid, long offset) throws Exception {
        sink.flush();
        Path marker = Settings.RUN.resolve(scenario + ".hold");
        Events.log(scenario, "worker pid " + pid + " flushed " + offset % Settings.BATCH + " records of the open batch, next offset " + offset + ", nothing committed");
        Files.createFile(marker);
        while (Files.exists(marker)) {
            Thread.sleep(100);
        }
    }
}
