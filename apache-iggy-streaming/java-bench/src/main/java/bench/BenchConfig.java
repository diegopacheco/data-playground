package bench;

import java.util.Map;

public record BenchConfig(String broker, String address, String topic, int rate, int size, double seconds,
                          double warmupSeconds, int partitions, int batchCap, double drainSeconds) {

    public static final String STREAM = "bench";

    public static BenchConfig fromEnv(Map<String, String> env) {
        String broker = env.get("BROKER");
        if (!"iggy".equals(broker) && !"kafka".equals(broker)) {
            throw new IllegalArgumentException("BROKER must be iggy or kafka, got " + broker);
        }
        return new BenchConfig(
                broker,
                env.get(broker.equals("iggy") ? "IGGY_ADDRESS" : "KAFKA_BOOTSTRAP"),
                env.get("TOPIC"),
                Integer.parseInt(env.getOrDefault("RATE", "1000")),
                Integer.parseInt(env.getOrDefault("SIZE", "100")),
                Double.parseDouble(env.getOrDefault("SECONDS", "10")),
                Double.parseDouble(env.getOrDefault("WARMUP_SECONDS", "2")),
                Integer.parseInt(env.getOrDefault("PARTITIONS", "3")),
                Integer.parseInt(env.getOrDefault("BATCH_CAP", "1000")),
                Double.parseDouble(env.getOrDefault("DRAIN_SECONDS", "15")));
    }

    public long warmupMicros() {
        return (long) (warmupSeconds * 1_000_000);
    }
}
