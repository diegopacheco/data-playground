package bench;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class StreamBenchTest {

    private static void feed(OrderTracker tracker, int partitions, long... seqs) {
        for (long seq : seqs) {
            tracker.observe((int) (seq % partitions), seq);
        }
    }

    @Test
    void payloadCarriesSeqAndSendTimestampAndHasTheExactWireSize() {
        byte[] data = Payload.encode(42, 1_794_000_000_123_456L, 1024);
        assertEquals(1024, data.length);
        assertEquals(new Payload.Stamp(42, 1_794_000_000_123_456L), Payload.decode(data));
    }

    @Test
    void payloadSmallerThanHeaderIsRefusedSoNoRunSilentlyDropsTheTimestamp() {
        assertThrows(IllegalArgumentException.class, () -> Payload.encode(1, 1, Payload.HEADER_SIZE - 1));
    }

    @Test
    void payloadIsByteCompatibleWithThePythonClient() {
        byte[] data = Payload.encode(1, 2, 16);
        assertArrayEquals(new byte[] {0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 2}, data);
    }

    @Test
    void everyMessageOnceInOrderIsComplete() {
        OrderTracker tracker = new OrderTracker(3);
        feed(tracker, 3, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9);
        assertTrue(tracker.complete(10));
    }

    @Test
    void aLostMessageIsAGapAndTheRunIsNotComplete() {
        OrderTracker tracker = new OrderTracker(3);
        feed(tracker, 3, 0, 1, 2, 4, 5, 6, 7, 8, 9);
        assertEquals(1, tracker.gaps());
        assertFalse(tracker.complete(10));
    }

    @Test
    void aDuplicateOrReorderedMessageIsCaughtEvenWhenTheCountMatches() {
        OrderTracker tracker = new OrderTracker(3);
        feed(tracker, 3, 0, 1, 2, 6, 3, 4, 5, 7, 8, 9);
        assertEquals(1, tracker.backwards());
        assertFalse(tracker.complete(10));
    }

    @Test
    void interleavingAcrossPartitionsIsStillInOrderPerPartition() {
        OrderTracker tracker = new OrderTracker(3);
        feed(tracker, 3, 2, 0, 5, 1, 3, 8, 4, 6, 7, 9);
        assertTrue(tracker.complete(10));
    }

    @Test
    void messageOnTheWrongPartitionIsMisrouted() {
        OrderTracker tracker = new OrderTracker(3);
        tracker.observe(0, 1);
        assertEquals(1, tracker.misrouted());
        assertFalse(tracker.inOrder());
    }

    @Test
    void missingTailMessagesFailCompletenessEvenWithoutGaps() {
        OrderTracker tracker = new OrderTracker(3);
        feed(tracker, 3, 0, 1, 2, 3, 4, 5, 6, 7);
        assertTrue(tracker.inOrder());
        assertFalse(tracker.complete(10));
    }

    @Test
    void nearestRankPercentiles() {
        long[] values = new long[100];
        for (int i = 0; i < 100; i++) {
            values[i] = i + 1;
        }
        assertEquals(50, Latencies.percentile(values, 50));
        assertEquals(99, Latencies.percentile(values, 99));
        Latencies latencies = new Latencies();
        for (long v : new long[] {3000, 1000, 2000, 4000}) {
            latencies.add(v);
        }
        assertEquals(new Latencies.Summary(4, 2.0, 4.0, 4.0, 4.0), latencies.summarize());
    }

    @Test
    void latencyIsReceiveTimeMinusTheSendTimestampWrittenInThePayload() {
        Recorder recorder = new Recorder(1, 0, 1);
        long sentAt = Payload.nowUs() - 5_000;
        recorder.observe(0, Payload.encode(0, sentAt, 100), sentAt + 1_000, sentAt + 5_000);
        assertArrayEquals(new long[] {5_000}, recorder.latencies().snapshot());
        assertEquals(0, recorder.tsViolations());
    }

    @Test
    void brokerTimestampOutsideSendAndReceiveIsFlagged() {
        Recorder recorder = new Recorder(1, 0, 1);
        recorder.observe(0, Payload.encode(0, 1_000, 100), 500, 2_000);
        recorder.observe(0, Payload.encode(1, 1_000, 100), 3_000, 2_000);
        assertEquals(2, recorder.tsViolations());
    }

    @Test
    void millisecondBrokerClockIsComparedAtMillisecondGranularity() {
        Recorder recorder = new Recorder(1, 0, 1000);
        recorder.observe(0, Payload.encode(0, 1_000_700, 100), 1_000_000, 1_001_200);
        assertEquals(0, recorder.tsViolations());
    }

    @Test
    void warmupMessagesCountForCompletenessButNotForLatency() {
        Recorder recorder = new Recorder(1, 10_000, 1);
        recorder.observe(0, Payload.encode(0, 9_000, 100), 9_500, 9_900);
        recorder.observe(0, Payload.encode(1, 10_000, 100), 10_100, 10_300);
        assertEquals(2, recorder.received());
        assertArrayEquals(new long[] {300}, recorder.latencies().snapshot());
    }

    @Test
    void pacerKeepsTheFixedRateAndCapsBursts() {
        assertEquals(500, Pacer.due(0.5, 1000, 0, 1000));
        assertEquals(0, Pacer.due(0.5, 1000, 500, 1000));
        assertEquals(200, Pacer.due(10.0, 1000, 0, 200));
        assertEquals(300, Pacer.due(0.0, 0, 0, 300));
    }

    @Test
    void iggyMessageHeaderDeclaresTheRealPayloadLength() {
        byte[] payload = Payload.encode(7, 9, 100);
        assertEquals(100L, IggyBench.message(payload).header().payloadLength());
    }

    @Test
    void kafkaClientsUseTheDocumentedDurabilityAndLatencySettings() {
        assertEquals("all", KafkaBench.producerProps("k:9092").get("acks"));
        assertEquals("0", KafkaBench.producerProps("k:9092").get("linger.ms"));
        assertEquals("true", KafkaBench.producerProps("k:9092").get("enable.idempotence"));
        assertEquals("100", KafkaBench.consumerProps("k:9092").get("fetch.max.wait.ms"));
        assertEquals("LogAppendTime", KafkaBench.TOPIC_CONFIGS.get("message.timestamp.type"));
    }

    @Test
    void resultJsonKeepsTheSameKeysAndTypesThePythonHarnessParses() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("a", 1);
        result.put("b", "x\"y");
        result.put("c", null);
        result.put("d", Map.of("e", true));
        assertEquals("{\"a\":1,\"b\":\"x\\\"y\",\"c\":null,\"d\":{\"e\":true}}", Result.toJson(result));
    }

    @Test
    void configReadsTheBrokerAddressForTheSelectedBroker() {
        BenchConfig cfg = BenchConfig.fromEnv(Map.of("BROKER", "iggy", "IGGY_ADDRESS", "iggy:8090", "TOPIC", "t"));
        assertEquals("iggy:8090", cfg.address());
        assertEquals(3, cfg.partitions());
        assertThrows(IllegalArgumentException.class, () -> BenchConfig.fromEnv(Map.of("BROKER", "pulsar")));
    }
}
