package bench;

import java.util.Arrays;

public final class Latencies {

    public record Summary(int samples, double p50Ms, double p95Ms, double p99Ms, double maxMs) {
    }

    private long[] values = new long[1 << 16];
    private int size;

    public void add(long micros) {
        if (size == values.length) {
            values = Arrays.copyOf(values, size * 2);
        }
        values[size++] = micros;
    }

    public int size() {
        return size;
    }

    public long[] snapshot() {
        return Arrays.copyOf(values, size);
    }

    public Summary summarize() {
        long[] sorted = snapshot();
        Arrays.sort(sorted);
        return new Summary(size, percentile(sorted, 50) / 1000.0, percentile(sorted, 95) / 1000.0,
                percentile(sorted, 99) / 1000.0, sorted[sorted.length - 1] / 1000.0);
    }

    public static long percentile(long[] sorted, double pct) {
        if (sorted.length == 0) {
            throw new IllegalArgumentException("no samples");
        }
        long rank = Math.max(1, (long) Math.ceil(sorted.length * pct / 100.0));
        return sorted[(int) rank - 1];
    }
}
