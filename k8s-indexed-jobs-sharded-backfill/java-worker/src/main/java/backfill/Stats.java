package backfill;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;

public record Stats(long count, long total, long min, long max) {

    public Stats merge(Stats other) {
        return new Stats(count + other.count, total + other.total, Math.min(min, other.min), Math.max(max, other.max));
    }

    public static Map<String, Stats> mergeAll(Collection<Map<String, Stats>> parts) {
        Map<String, Stats> merged = new HashMap<>();
        parts.forEach(part -> part.forEach((category, stats) -> merged.merge(category, stats, Stats::merge)));
        return merged;
    }

    public static long rowCount(Map<String, Stats> aggregates) {
        return aggregates.values().stream().mapToLong(Stats::count).sum();
    }
}
