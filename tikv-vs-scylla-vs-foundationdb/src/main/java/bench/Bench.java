package bench;

import java.nio.file.Files;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

public class Bench {

    record Loaded(double seconds, Verify.Digest digest, int keys, int ranges) {
    }

    public static void main(String[] args) {
        try {
            run();
            System.exit(0);
        } catch (Throwable e) {
            e.printStackTrace();
            System.exit(1);
        }
    }

    private static void run() throws Exception {
        Dataset dataset = Dataset.read();
        String datasetSha = Verify.sha256(Files.readAllBytes(Settings.DATASET));
        int valueBytes = dataset.entry(0).value().length;
        System.out.println("dataset " + dataset.size() + " rows sha256 " + datasetSha);

        List<Store> stores = Store.openAll();
        Map<Store, Loaded> loaded = new LinkedHashMap<>();
        for (Store store : stores) {
            loaded.put(store, load(store, dataset, datasetSha));
        }

        Map<Store, List<Runner.Sample>> points = new LinkedHashMap<>();
        Map<Store, List<Runner.Sample>> scans = new LinkedHashMap<>();
        for (int round = 1; round <= Settings.ROUNDS; round++) {
            int[] warmPoints = dataset.positions(Settings.WARMUP_POINT, 1, 100 + round);
            int[] readPoints = dataset.positions(Settings.POINT_READS, 1, 200 + round);
            int[] warmScans = dataset.positions(Settings.WARMUP_SCAN, Settings.RANGE_LENGTH, 300 + round);
            int[] readScans = dataset.positions(Settings.RANGE_SCANS, Settings.RANGE_LENGTH, 400 + round);
            for (Store store : stores) {
                Runner.run(warmPoints.length, Settings.CONCURRENCY, i -> point(store, dataset, warmPoints[i]));
                points.computeIfAbsent(store, s -> new ArrayList<>())
                        .add(Runner.run(readPoints.length, Settings.CONCURRENCY, i -> point(store, dataset, readPoints[i])));
                Runner.run(warmScans.length, Settings.CONCURRENCY, i -> scan(store, dataset, warmScans[i]));
                scans.computeIfAbsent(store, s -> new ArrayList<>())
                        .add(Runner.run(readScans.length, Settings.CONCURRENCY, i -> scan(store, dataset, readScans[i])));
                System.out.println("round " + round + " " + store.name() + " done");
            }
        }

        List<String> results = new ArrayList<>();
        for (Store store : stores) {
            Stats point = Stats.of("point_read", points.get(store));
            Stats scan = Stats.of("range_scan", scans.get(store));
            System.out.println("== " + store.name() + " " + store.version());
            System.out.println("   " + point.line());
            System.out.println("   " + scan.line());
            results.add(json(store, loaded.get(store), dataset.size(), point, scan));
            store.close();
        }
        Files.writeString(Settings.RESULTS, json(datasetSha, dataset.size(), valueBytes, results));
        System.out.println("results written to " + Settings.RESULTS);
    }

    private static Loaded load(Store store, Dataset dataset, String datasetSha) throws InterruptedException {
        store.reset();
        List<List<Store.Entry>> batches = dataset.batches();
        Runner.Sample sample = Runner.run(batches.size(), Settings.CONCURRENCY, i -> {
            store.load(batches.get(i));
            return true;
        });
        Verify.Digest digest = Verify.digest(store);
        Loaded loaded = new Loaded(sample.wallNanos() / 1e9, digest, Verify.matchingKeys(store, dataset), Verify.matchingRanges(store, dataset));
        System.out.printf(Locale.ROOT, "%-13s loaded in %.2fs, full scan %d rows sha256 %s, sampled keys %d/%d, sampled ranges %d/%d%n",
                store.name(), loaded.seconds(), digest.rows(), digest.sha256(), loaded.keys(), Settings.SAMPLE_KEYS, loaded.ranges(), Settings.SAMPLE_RANGES);
        if (sample.errors() > 0 || !digest.sha256().equals(datasetSha) || loaded.keys() != Settings.SAMPLE_KEYS || loaded.ranges() != Settings.SAMPLE_RANGES) {
            System.err.println("ERROR: " + store.name() + " does not hold the dataset, refusing to time it");
            System.exit(1);
        }
        return loaded;
    }

    private static boolean point(Store store, Dataset dataset, int position) {
        Store.Entry expected = dataset.entry(position);
        return Arrays.equals(expected.value(), store.get(expected.key()));
    }

    private static boolean scan(Store store, Dataset dataset, int position) {
        List<Store.Entry> entries = store.scan(dataset.entry(position).key(), Settings.RANGE_LENGTH);
        return entries.size() == Settings.RANGE_LENGTH
                && entries.get(0).key().equals(dataset.entry(position).key())
                && entries.get(entries.size() - 1).key().equals(dataset.entry(position + Settings.RANGE_LENGTH - 1).key());
    }

    private static String json(Store store, Loaded loaded, int rows, Stats point, Stats scan) {
        return String.format(Locale.ROOT,
                "{\"name\":\"%s\",\"version\":\"%s\",\"api\":\"%s\",\"load_seconds\":%.3f,\"load_rows_per_second\":%.1f,"
                        + "\"full_scan_rows\":%d,\"full_scan_sha256\":\"%s\",\"sample_keys_matching\":%d,\"sample_ranges_matching\":%d,\"operations\":[%s,%s]}",
                store.name(), store.version(), store.api(), loaded.seconds(), rows / loaded.seconds(),
                loaded.digest().rows(), loaded.digest().sha256(), loaded.keys(), loaded.ranges(), point.json(), scan.json());
    }

    private static String json(String datasetSha, int rows, int valueBytes, List<String> results) {
        return "{\"generated_at\":\"" + Instant.now() + "\","
                + "\"setup\":{\"rows\":" + rows + ",\"key_bytes\":" + Verify.FIRST_KEY.length() + ",\"value_bytes\":" + valueBytes
                + ",\"concurrency\":" + Settings.CONCURRENCY + ",\"rounds\":" + Settings.ROUNDS
                + ",\"point_reads\":" + Settings.ROUNDS * Settings.POINT_READS + ",\"range_scans\":" + Settings.ROUNDS * Settings.RANGE_SCANS
                + ",\"range_length\":" + Settings.RANGE_LENGTH
                + ",\"warmup_point_reads\":" + Settings.ROUNDS * Settings.WARMUP_POINT + ",\"warmup_range_scans\":" + Settings.ROUNDS * Settings.WARMUP_SCAN
                + ",\"load_batch\":" + Settings.LOAD_BATCH + ",\"sample_keys\":" + Settings.SAMPLE_KEYS + ",\"sample_ranges\":" + Settings.SAMPLE_RANGES
                + ",\"scylla_bucket_rows\":" + Settings.SCYLLA_BUCKET_ROWS
                + ",\"java\":\"" + Runtime.version() + "\",\"store_limits\":\"" + Settings.LIMITS + "\""
                + ",\"note\":\"single node, one laptop, containers in a VM, no replication: numbers are relative, not absolute\"},"
                + "\"dataset_sha256\":\"" + datasetSha + "\","
                + "\"stores\":[" + results.stream().collect(Collectors.joining(",")) + "]}\n";
    }
}
