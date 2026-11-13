package producer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class BatchWriterTest {

    record Put(String key, String body) {
    }

    static final class RecordingStore implements ObjectStore {
        final List<Put> puts = new ArrayList<>();

        @Override
        public void createBucket() {
        }

        @Override
        public synchronized void put(String key, byte[] body, String contentType) {
            puts.add(new Put(key, new String(body, StandardCharsets.UTF_8)));
        }
    }

    final Clock clock = Clock.fixed(Instant.ofEpochMilli(1_800_000_000_000L), ZoneOffset.UTC);

    @Test
    void readyMarkerIsWrittenLastSoTheEtlNeverSeesAHalfWrittenBatch() throws Exception {
        RecordingStore store = new RecordingStore();
        new BatchWriter(store, 3, 10, clock).write("s1-000001");
        assertEquals(4, store.puts.size());
        assertEquals("input/s1-000001/_READY", store.puts.getLast().key());
        for (Put part : store.puts.subList(0, 3)) {
            assertTrue(part.key().matches("input/s1-000001/part-[0-2]\\.jsonl"), part.key());
        }
    }

    @Test
    void markerListsEveryPartFileAndTheEventCountTheEtlMustAccountFor() throws Exception {
        RecordingStore store = new RecordingStore();
        String marker = new BatchWriter(store, 2, 7, clock).write("s1-000002");
        assertEquals("{\"batch_id\":\"s1-000002\",\"files\":[\"input/s1-000002/part-0.jsonl\","
                + "\"input/s1-000002/part-1.jsonl\"],\"events\":14,\"ready_at_ms\":1800000000000}", marker);
        Set<String> ids = new HashSet<>();
        for (Put part : store.puts.subList(0, 2)) {
            for (String line : part.body().strip().split("\n")) {
                ids.add(line.substring(line.indexOf("\"event_id\":\"") + 12, line.indexOf("\",\"batch_id\"")));
            }
        }
        assertEquals(14, ids.size());
    }

    @Test
    void batchIdsSortInProductionOrder() {
        assertTrue(BatchWriter.batchId("s1", 9).compareTo(BatchWriter.batchId("s1", 10)) < 0);
    }
}
