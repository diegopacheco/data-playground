package sales;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Properties;
import java.util.Set;

public final class CdcConsumer implements Runnable {

    private final ObjectMapper json = JsonMapper.builder().build();
    private final CassandraStore cassandra;
    private final ChangeLog log;

    public CdcConsumer(CassandraStore cassandra, ChangeLog log) {
        this.cassandra = cassandra;
        this.log = log;
    }

    @Override
    public void run() {
        Properties props = new Properties();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, Settings.KAFKA_BOOTSTRAP);
        props.put(ConsumerConfig.GROUP_ID_CONFIG, Settings.GROUP_ID);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
        props.put(ConsumerConfig.METADATA_MAX_AGE_CONFIG, "5000");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
            consumer.subscribe(List.of(Settings.TOPIC));
            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));
                if (records.isEmpty()) {
                    continue;
                }
                Set<String> touched = new HashSet<>();
                for (ConsumerRecord<String, String> record : records) {
                    if (record.value() != null) {
                        apply(json.readTree(record.value()), touched);
                    }
                }
                cassandra.recompute(touched);
                consumer.commitSync();
            }
        }
    }

    private void apply(JsonNode event, Set<String> touched) {
        String op = event.path("op").asString();
        JsonNode before = event.path("before");
        JsonNode after = event.path("after");
        if (!before.isNull() && !before.isMissingNode()) {
            touched.add(before.get("category").asString());
        }
        if (!after.isNull() && !after.isMissingNode()) {
            touched.add(after.get("category").asString());
        }
        JsonNode row = "d".equals(op) ? before : after;
        if ("d".equals(op)) {
            cassandra.delete(row.get("order_id").asInt());
        } else {
            cassandra.upsert(after);
        }
        log.add(new ChangeLog.Change(op, row.get("order_id").asInt(), row.get("category").asString(),
                describe(op, before, after), event.path("ts_ms").asLong(), System.currentTimeMillis()));
    }

    private String describe(String op, JsonNode before, JsonNode after) {
        return switch (op) {
            case "u" -> summary(before) + " -> " + summary(after);
            case "d" -> summary(before);
            default -> summary(after);
        };
    }

    private String summary(JsonNode row) {
        return row.get("category").asString() + " qty " + row.get("quantity").asInt() + " x " + row.get("price").asString();
    }
}
