package eos;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.TopicPartition;

final class Audit {
    static List<ConsumerRecord<String, String>> read(String topic, String isolation) {
        TopicPartition partition = new TopicPartition(topic, 0);
        List<ConsumerRecord<String, String>> records = new ArrayList<>();
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(Settings.consumer(isolation))) {
            consumer.assign(List.of(partition));
            consumer.seekToBeginning(List.of(partition));
            long end = consumer.endOffsets(List.of(partition)).get(partition);
            while (consumer.position(partition) < end) {
                consumer.poll(Duration.ofMillis(500)).forEach(records::add);
            }
        }
        return records;
    }

    static String report() throws Exception {
        List<String> scenarios = new ArrayList<>();
        int input = 0;
        for (String scenario : Settings.SCENARIOS) {
            List<String> expected = read(Settings.in(scenario), "read_committed").stream().map(ConsumerRecord::key).toList();
            input = expected.size();
            scenarios.add(scenario(scenario, expected));
        }
        return "{\"input\":" + input + ",\"batch\":" + Settings.BATCH + ",\"scenarios\":[" + String.join(",", scenarios) + "]}";
    }

    private static String scenario(String name, List<String> expected) throws Exception {
        List<ConsumerRecord<String, String>> committed = read(Settings.out(name), "read_committed");
        List<ConsumerRecord<String, String>> uncommitted = read(Settings.out(name), "read_uncommitted");
        Set<Long> visible = committed.stream().map(ConsumerRecord::offset).collect(Collectors.toSet());
        Map<String, List<ConsumerRecord<String, String>>> byId = new LinkedHashMap<>();
        uncommitted.forEach(r -> byId.computeIfAbsent(r.key(), k -> new ArrayList<>()).add(r));
        String repeated = byId.entrySet().stream().filter(e -> e.getValue().size() > 1)
            .map(e -> "{\"id\":" + e.getKey() + ",\"copies\":[" + e.getValue().stream()
                .map(r -> "{\"offset\":" + r.offset() + ",\"committed\":" + visible.contains(r.offset()) + "}")
                .collect(Collectors.joining(",")) + "]}")
            .collect(Collectors.joining(","));
        int batches = (expected.size() + Settings.BATCH - 1) / Settings.BATCH;
        int[] committedPerBatch = perBatch(committed, batches);
        int[] uncommittedPerBatch = perBatch(uncommitted, batches);
        List<String> bars = new ArrayList<>();
        for (int b = 0; b < batches; b++) {
            bars.add("{\"committed\":" + committedPerBatch[b] + ",\"uncommitted\":" + uncommittedPerBatch[b] + "}");
        }
        Path fenced = Settings.RUN.resolve(name + ".fenced");
        return "{\"name\":\"" + name + "\""
            + ",\"fenced\":" + (Files.exists(fenced) ? "\"" + Files.readString(fenced).trim() + "\"" : "null")
            + ",\"committed\":" + stats(committed, expected)
            + ",\"uncommitted\":" + stats(uncommitted, expected)
            + ",\"aborted\":" + (uncommitted.size() - committed.size())
            + ",\"batches\":[" + String.join(",", bars) + "]"
            + ",\"repeated\":[" + repeated + "]}";
    }

    private static int[] perBatch(List<ConsumerRecord<String, String>> records, int batches) {
        int[] counts = new int[batches];
        records.forEach(r -> counts[(Integer.parseInt(r.key()) - 1) / Settings.BATCH]++);
        return counts;
    }

    private static String stats(List<ConsumerRecord<String, String>> records, List<String> expected) {
        Set<String> ids = records.stream().map(ConsumerRecord::key).collect(Collectors.toSet());
        Set<String> missing = new HashSet<>(expected);
        missing.removeAll(ids);
        return "{\"records\":" + records.size() + ",\"distinct\":" + ids.size()
            + ",\"duplicates\":" + (records.size() - ids.size()) + ",\"missing\":" + missing.size() + "}";
    }
}
