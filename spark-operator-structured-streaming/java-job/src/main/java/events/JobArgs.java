package events;

import java.util.HashMap;
import java.util.Map;

public record JobArgs(String bootstrap, String topic, String table, String checkpoint, long triggerSeconds, String startingOffsets) {

    public static JobArgs parse(String[] args) {
        Map<String, String> values = new HashMap<>(Map.of(
                "bootstrap", "kafka-0.kafka:9092",
                "topic", "events",
                "starting-offsets", "latest",
                "trigger-seconds", "5"));
        for (int i = 0; i + 1 < args.length; i += 2) {
            if (!args[i].startsWith("--")) {
                throw new IllegalArgumentException("expected --name value, got " + args[i]);
            }
            values.put(args[i].substring(2), args[i + 1]);
        }
        if (args.length % 2 != 0) {
            throw new IllegalArgumentException("missing value for " + args[args.length - 1]);
        }
        long trigger = Long.parseLong(values.get("trigger-seconds"));
        if (trigger < 1) {
            throw new IllegalArgumentException("trigger-seconds must be at least 1");
        }
        return new JobArgs(values.get("bootstrap"), values.get("topic"), required(values, "table"),
                required(values, "checkpoint"), trigger, values.get("starting-offsets"));
    }

    private static String required(Map<String, String> values, String name) {
        String value = values.get(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("--" + name + " is required");
        }
        return value;
    }
}
