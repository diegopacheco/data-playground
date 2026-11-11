package backfill;

import java.util.Map;

@FunctionalInterface
public interface RangeReader {
    Map<String, Stats> read(TimeRange range);
}
