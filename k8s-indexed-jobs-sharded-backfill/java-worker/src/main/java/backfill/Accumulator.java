package backfill;

import java.util.HashMap;
import java.util.Map;

public final class Accumulator {

    private static final class Cell {
        long count;
        long total;
        long min = Long.MAX_VALUE;
        long max = Long.MIN_VALUE;
    }

    private final Map<String, Cell> cells = new HashMap<>();

    public void add(String category, long amount) {
        Cell cell = cells.computeIfAbsent(category, c -> new Cell());
        cell.count++;
        cell.total += amount;
        cell.min = Math.min(cell.min, amount);
        cell.max = Math.max(cell.max, amount);
    }

    public Map<String, Stats> result() {
        Map<String, Stats> out = new HashMap<>();
        cells.forEach((category, c) -> out.put(category, new Stats(c.count, c.total, c.min, c.max)));
        return out;
    }
}
