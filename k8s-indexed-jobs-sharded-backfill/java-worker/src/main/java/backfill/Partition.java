package backfill;

import java.time.LocalDate;
import java.time.ZoneOffset;

public record Partition(int index, LocalDate day, TimeRange window) {

    public static Partition of(LocalDate startDay, int index) {
        if (index < 0) {
            throw new IllegalArgumentException("index must be >= 0, got " + index);
        }
        LocalDate day = startDay.plusDays(index);
        return new Partition(index, day, new TimeRange(
                day.atStartOfDay().atOffset(ZoneOffset.UTC),
                day.plusDays(1).atStartOfDay().atOffset(ZoneOffset.UTC)));
    }
}
