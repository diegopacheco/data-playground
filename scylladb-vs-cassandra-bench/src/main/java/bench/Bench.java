package bench;

import java.nio.file.Files;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.stream.Collectors;

public class Bench {

    private static final int WARMUP = 10000;

    record Target(String name, int port, String resources) {
    }

    record Result(String name, String version, String resources, List<Stats> stats, List<Aggregate> aggregates) {

        String json() {
            return "{\"name\":\"" + name + "\",\"version\":\"" + version + "\",\"resources\":\"" + resources + "\","
                    + "\"operations\":[" + stats.stream().map(Stats::json).collect(Collectors.joining(",")) + "],"
                    + "\"aggregates\":[" + aggregates.stream().map(Aggregate::json).collect(Collectors.joining(",")) + "]}";
        }
    }

    public static void main(String[] args) throws Exception {
        List<Order> orders = Dataset.generate(Settings.BASE_CSV, Settings.ROWS);
        Dataset.write(Settings.BENCH_CSV, orders);
        List<String> categories = Dataset.categories(orders);
        System.out.println("generated " + orders.size() + " orders into " + Settings.BENCH_CSV);

        List<Target> targets = List.of(
                new Target("scylladb", Settings.SCYLLA_PORT, "--smp 1 --memory 1G --overprovisioned 1"),
                new Target("cassandra", Settings.CASSANDRA_PORT, "MAX_HEAP_SIZE=512M HEAP_NEWSIZE=128M"));
        List<Result> results = new ArrayList<>();
        for (Target target : targets) {
            results.add(bench(target, orders, categories));
        }

        boolean match = results.get(0).aggregates().equals(results.get(1).aggregates());
        Files.writeString(Settings.RESULTS, json(results, categories.size(), match));
        System.out.println("aggregates match: " + match);
        System.out.println("results written to " + Settings.RESULTS);
        if (!match) System.exit(1);
    }

    private static Result bench(Target target, List<Order> orders, List<String> categories) throws InterruptedException {
        try (Database db = new Database(target.name(), target.port())) {
            System.out.println("== " + target.name() + " " + db.version());
            db.resetSchema();
            List<Stats> stats = new ArrayList<>();
            int warmup = Math.min(WARMUP, orders.size());
            Runner.run("warmup", warmup, Settings.CONCURRENCY, i -> db.insert(orders.get(i)));
            stats.add(report(Runner.run("insert", orders.size(), Settings.CONCURRENCY, i -> db.insert(orders.get(i)))));
            List<Order> keys = readKeys(orders);
            Runner.run("warmup", Math.min(WARMUP, keys.size()), Settings.CONCURRENCY, i -> db.read(keys.get(i)));
            stats.add(report(Runner.run("point_read", keys.size(), Settings.CONCURRENCY, i -> db.read(keys.get(i)))));
            int aggOps = Settings.AGG_ROUNDS * categories.size();
            stats.add(report(Runner.run("aggregate", aggOps, Settings.AGG_CONCURRENCY, i -> db.aggregate(categories.get(i % categories.size())))));
            List<Aggregate> aggregates = categories.stream().map(db::aggregateNow).toList();
            aggregates.forEach(a -> System.out.println("   " + a.json()));
            return new Result(target.name(), db.version(), target.resources(), stats, aggregates);
        }
    }

    private static List<Order> readKeys(List<Order> orders) {
        Random random = new Random(42);
        List<Order> keys = new ArrayList<>(Settings.READS);
        for (int i = 0; i < Settings.READS; i++) {
            keys.add(orders.get(random.nextInt(orders.size())));
        }
        return keys;
    }

    private static Stats report(Stats stats) {
        System.out.println("   " + stats.line());
        return stats;
    }

    private static String json(List<Result> results, int categories, boolean match) {
        return "{\"generated_at\":\"" + Instant.now() + "\","
                + "\"setup\":{\"rows\":" + Settings.ROWS + ",\"reads\":" + Settings.READS + ",\"warmup_ops\":" + WARMUP
                + ",\"aggregate_ops\":" + Settings.AGG_ROUNDS * categories + ",\"categories\":" + categories
                + ",\"concurrency\":" + Settings.CONCURRENCY + ",\"aggregate_concurrency\":" + Settings.AGG_CONCURRENCY
                + ",\"driver\":\"org.apache.cassandra:java-driver-core:4.19.3\",\"java\":\"" + Runtime.version() + "\""
                + ",\"note\":\"single-node laptop bench in podman with constrained resources\"},"
                + "\"aggregates_match\":" + match + ","
                + "\"databases\":[" + results.stream().map(Result::json).collect(Collectors.joining(",")) + "]}\n";
    }
}
