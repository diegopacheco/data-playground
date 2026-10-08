package sales;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class ChangeLog {

    public record Change(String op, int orderId, String category, String detail, long sourceMs, long appliedMs) {
    }

    private static final int LIMIT = 50;
    private final Deque<Change> recent = new ArrayDeque<>();
    private final Map<String, Long> counts = new TreeMap<>(Map.of("r", 0L, "c", 0L, "u", 0L, "d", 0L));

    public synchronized void add(Change change) {
        counts.merge(change.op(), 1L, Long::sum);
        recent.addFirst(change);
        if (recent.size() > LIMIT) {
            recent.removeLast();
        }
    }

    public synchronized List<Change> recent() {
        return new ArrayList<>(recent);
    }

    public synchronized Map<String, Long> counts() {
        return new TreeMap<>(counts);
    }
}
