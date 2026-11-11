package backfill;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public record TimeRange(OffsetDateTime start, OffsetDateTime end) {

    public List<TimeRange> split(int parts) {
        if (parts < 1) {
            throw new IllegalArgumentException("parts must be >= 1, got " + parts);
        }
        Duration step = Duration.between(start, end).dividedBy(parts);
        List<TimeRange> ranges = new ArrayList<>(parts);
        for (int i = 0; i < parts; i++) {
            OffsetDateTime from = start.plus(step.multipliedBy(i));
            OffsetDateTime to = i == parts - 1 ? end : start.plus(step.multipliedBy(i + 1));
            ranges.add(new TimeRange(from, to));
        }
        return ranges;
    }
}
