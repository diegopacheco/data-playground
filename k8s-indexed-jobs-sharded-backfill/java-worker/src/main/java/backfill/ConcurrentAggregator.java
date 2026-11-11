package backfill;

import java.util.List;
import java.util.Map;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

public final class ConcurrentAggregator {

    private ConcurrentAggregator() {
    }

    public static Map<String, Stats> aggregate(List<TimeRange> ranges, RangeReader reader) throws InterruptedException {
        try (var scope = StructuredTaskScope.open()) {
            List<Subtask<Map<String, Stats>>> tasks = ranges.stream()
                    .map(range -> scope.fork(() -> reader.read(range)))
                    .toList();
            scope.join();
            return Stats.mergeAll(tasks.stream().map(Subtask::get).toList());
        }
    }
}
