package clicks;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.LongStream;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.runtime.checkpoint.OperatorSubtaskState;
import org.apache.flink.runtime.state.KeyGroupRangeAssignment;
import org.apache.flink.streaming.api.operators.KeyedProcessOperator;
import org.apache.flink.streaming.runtime.streamrecord.StreamRecord;
import org.apache.flink.streaming.util.AbstractStreamOperatorTestHarness;
import org.apache.flink.streaming.util.KeyedOneInputStreamOperatorTestHarness;
import org.junit.jupiter.api.Test;

class ClickCounterTest {

    private static final int USERS = 10;
    private static final int MAX_PARALLELISM = 128;

    private static KeyedOneInputStreamOperatorTestHarness<String, Click, String> harness(String version, int parallelism, int subtask) throws Exception {
        return new KeyedOneInputStreamOperatorTestHarness<>(
            new KeyedProcessOperator<>(new ClickCounter("java", version)), Click::user, Types.STRING, MAX_PARALLELISM, parallelism, subtask);
    }

    private static void feed(KeyedOneInputStreamOperatorTestHarness<String, Click, String> h, long from, long to) throws Exception {
        for (long seq = from; seq < to; seq++) {
            Click click = new ClickGenerator(USERS).map(seq);
            if (h.getEnvironment().getTaskInfo().getIndexOfThisSubtask() == subtaskOf(click.user(), h)) {
                h.processElement(new StreamRecord<>(click));
            }
        }
    }

    private static int subtaskOf(String user, KeyedOneInputStreamOperatorTestHarness<String, Click, String> h) {
        int parallelism = h.getEnvironment().getTaskInfo().getNumberOfParallelSubtasks();
        return KeyGroupRangeAssignment.assignKeyToParallelOperator(user, MAX_PARALLELISM, parallelism);
    }

    private static Map<String, Long> lastCounts(List<String> lines) {
        Map<String, Long> counts = new HashMap<>();
        for (String line : lines) {
            String user = line.replaceAll(".* user=(\\S+) .*", "$1");
            counts.put(user, Long.parseLong(line.replaceAll(".* count=(\\d+)$", "$1")));
        }
        return counts;
    }

    private static List<String> output(KeyedOneInputStreamOperatorTestHarness<String, Click, String> h) {
        return h.extractOutputValues();
    }

    @Test
    void countsPerUserMatchHowManyClicksThatUserMade() throws Exception {
        try (var h = harness("v1", 1, 0)) {
            h.open();
            feed(h, 0, 95);
            Map<String, Long> counts = lastCounts(output(h));
            assertEquals(10, counts.get("user-0"));
            assertEquals(9, counts.get("user-9"));
            assertEquals(LongStream.range(0, 95).count(), counts.values().stream().mapToLong(Long::longValue).sum());
        }
    }

    @Test
    void restoringASnapshotIntoANewVersionContinuesTheCountInsteadOfStartingAtOne() throws Exception {
        OperatorSubtaskState snapshot;
        try (var before = harness("v1", 1, 0)) {
            before.open();
            feed(before, 0, 50);
            snapshot = before.snapshot(1, 1);
        }
        try (var after = harness("v2", 1, 0)) {
            after.initializeState(snapshot);
            after.open();
            feed(after, 50, 60);
            List<String> lines = output(after);
            assertEquals("CLICKS job=java version=v2 user=user-0 seq=50 count=6", lines.getFirst());
            assertEquals(6, lastCounts(lines).get("user-9"));
        }
    }

    @Test
    void withoutRestoredStateTheCountStartsOverAtOne() throws Exception {
        try (var fresh = harness("v2", 1, 0)) {
            fresh.open();
            feed(fresh, 50, 60);
            assertEquals("CLICKS job=java version=v2 user=user-0 seq=50 count=1", output(fresh).getFirst());
        }
    }

    @Test
    void rescalingOneToTwoSubtasksKeepsEveryUserCount() throws Exception {
        OperatorSubtaskState snapshot;
        try (var single = harness("v1", 1, 0)) {
            single.open();
            feed(single, 0, 100);
            snapshot = single.snapshot(1, 1);
        }
        Map<String, Long> counts = new HashMap<>();
        for (int subtask = 0; subtask < 2; subtask++) {
            OperatorSubtaskState part = AbstractStreamOperatorTestHarness.repartitionOperatorState(snapshot, MAX_PARALLELISM, 1, 2, subtask);
            try (var h = harness("v2", 2, subtask)) {
                h.initializeState(part);
                h.open();
                feed(h, 100, 110);
                counts.putAll(lastCounts(output(h)));
            }
        }
        assertEquals(USERS, counts.size());
        counts.values().forEach(c -> assertEquals(11L, c));
    }
}
