package backfill;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.StructuredTaskScope;
import org.junit.jupiter.api.Test;

class ConcurrentAggregatorTest {

    private static final List<TimeRange> RANGES = Partition.of(LocalDate.of(2026, 10, 1), 0).window().split(4);

    private static Map<String, Stats> rowsFor(TimeRange range) {
        Accumulator acc = new Accumulator();
        int hour = range.start().getHour();
        acc.add("books", hour + 10);
        acc.add("games", hour + 1);
        acc.add("books", 2);
        return acc.result();
    }

    @Test
    void concurrentSubRangeResultsMergeToTheSameTotalsAsReadingSequentially() throws InterruptedException {
        Map<String, Stats> sequential = Stats.mergeAll(RANGES.stream().map(ConcurrentAggregatorTest::rowsFor).toList());
        Map<String, Stats> concurrent = ConcurrentAggregator.aggregate(RANGES, ConcurrentAggregatorTest::rowsFor);
        assertEquals(sequential, concurrent);
        assertEquals(new Stats(8, 2 * 4 + 10 * 4 + 36, 2, 28), concurrent.get("books"));
        assertEquals(12, Stats.rowCount(concurrent));
    }

    @Test
    void eachSubRangeRunsOnItsOwnVirtualThread() throws InterruptedException {
        Set<Long> threads = ConcurrentHashMap.newKeySet();
        Set<Boolean> virtual = ConcurrentHashMap.newKeySet();
        ConcurrentAggregator.aggregate(RANGES, range -> {
            threads.add(Thread.currentThread().threadId());
            virtual.add(Thread.currentThread().isVirtual());
            return rowsFor(range);
        });
        assertEquals(4, threads.size());
        assertEquals(Set.of(true), virtual);
    }

    @Test
    void oneFailingSubRangeFailsTheWholePartitionSoNoPartialAggregateIsEverWritten() {
        StructuredTaskScope.FailedException failed = assertThrows(StructuredTaskScope.FailedException.class,
                () -> ConcurrentAggregator.aggregate(RANGES, range -> {
                    if (range.equals(RANGES.get(2))) {
                        throw new IllegalStateException("sub-range read failed");
                    }
                    return rowsFor(range);
                }));
        assertTrue(failed.getCause() instanceof IllegalStateException);
    }
}
