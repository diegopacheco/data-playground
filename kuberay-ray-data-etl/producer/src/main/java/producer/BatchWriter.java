package producer;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.Collectors;

public final class BatchWriter {

    public static final String READY = "_READY";

    private final ObjectStore store;
    private final int filesPerBatch;
    private final int eventsPerFile;
    private final Clock clock;

    public BatchWriter(ObjectStore store, int filesPerBatch, int eventsPerFile, Clock clock) {
        this.store = store;
        this.filesPerBatch = filesPerBatch;
        this.eventsPerFile = eventsPerFile;
        this.clock = clock;
    }

    public static String batchId(String runId, int seq) {
        return "%s-%06d".formatted(runId, seq);
    }

    public String write(String batchId) throws Exception {
        long ts = clock.millis();
        List<String> keys = new ArrayList<>();
        try (ExecutorService threads = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> parts = new ArrayList<>();
            for (int file = 0; file < filesPerBatch; file++) {
                String key = "input/" + batchId + "/part-" + file + ".jsonl";
                keys.add(key);
                int index = file;
                parts.add(threads.submit(() -> store.put(key, body(batchId, index, ts), "application/x-ndjson")));
            }
            for (Future<?> part : parts) {
                part.get();
            }
        }
        String marker = marker(batchId, keys, clock.millis());
        store.put("input/" + batchId + "/" + READY, marker.getBytes(StandardCharsets.UTF_8), "application/json");
        return marker;
    }

    private byte[] body(String batchId, int file, long ts) {
        return EventGenerator.toJsonLines(EventGenerator.generate(batchId, file, eventsPerFile, ts))
                .getBytes(StandardCharsets.UTF_8);
    }

    private String marker(String batchId, List<String> keys, long readyAt) {
        String files = keys.stream().map(k -> "\"" + k + "\"").collect(Collectors.joining(","));
        return "{\"batch_id\":\"" + batchId + "\",\"files\":[" + files + "],\"events\":"
                + (long) filesPerBatch * eventsPerFile + ",\"ready_at_ms\":" + readyAt + "}";
    }
}
