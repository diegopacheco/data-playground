package backfill;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class PartitionTest {

    private static final LocalDate START = LocalDate.of(2026, 10, 1);

    @Test
    void everyIndexOwnsADistinctConsecutiveDaySoNoTwoPodsBackfillTheSamePartition() {
        Set<LocalDate> days = new HashSet<>();
        for (int i = 0; i < 12; i++) {
            Partition p = Partition.of(START, i);
            assertEquals(START.plusDays(i), p.day());
            days.add(p.day());
        }
        assertEquals(12, days.size());
    }

    @Test
    void windowIsOneHalfOpenUtcDay() {
        Partition p = Partition.of(START, 2);
        assertEquals(OffsetDateTime.of(2026, 10, 3, 0, 0, 0, 0, ZoneOffset.UTC), p.window().start());
        assertEquals(OffsetDateTime.of(2026, 10, 4, 0, 0, 0, 0, ZoneOffset.UTC), p.window().end());
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 3, 4, 7, 24})
    void subRangesTileTheDayWithoutGapsOrOverlapsSoEachRowIsReadOnce(int parts) {
        TimeRange window = Partition.of(START, 0).window();
        List<TimeRange> ranges = window.split(parts);
        assertEquals(parts, ranges.size());
        assertEquals(window.start(), ranges.getFirst().start());
        assertEquals(window.end(), ranges.getLast().end());
        for (int i = 1; i < ranges.size(); i++) {
            assertEquals(ranges.get(i - 1).end(), ranges.get(i).start());
            assertTrue(ranges.get(i).start().isBefore(ranges.get(i).end()));
        }
    }

    @Test
    void invalidInputsFailLoud() {
        assertThrows(IllegalArgumentException.class, () -> Partition.of(START, -1));
        assertThrows(IllegalArgumentException.class, () -> Partition.of(START, 0).window().split(0));
    }
}
