package bench;

import java.util.Arrays;
import java.util.Locale;

public record Stats(String operation, int ops, int errors, double seconds, double throughput, double p50, double p95, double p99, double max) {

    public static Stats of(String operation, long[] latencyNanos, int errors, long wallNanos) {
        long[] sorted = latencyNanos.clone();
        Arrays.sort(sorted);
        double seconds = wallNanos / 1e9;
        return new Stats(operation, sorted.length, errors, seconds, sorted.length / seconds,
                millis(sorted, 0.50), millis(sorted, 0.95), millis(sorted, 0.99), sorted[sorted.length - 1] / 1e6);
    }

    private static double millis(long[] sorted, double q) {
        int index = (int) Math.ceil(q * sorted.length) - 1;
        return sorted[Math.max(0, index)] / 1e6;
    }

    public String json() {
        return String.format(Locale.ROOT,
                "{\"operation\":\"%s\",\"ops\":%d,\"errors\":%d,\"seconds\":%.3f,\"throughput\":%.1f,\"p50_ms\":%.3f,\"p95_ms\":%.3f,\"p99_ms\":%.3f,\"max_ms\":%.3f}",
                operation, ops, errors, seconds, throughput, p50, p95, p99, max);
    }

    public String line() {
        return String.format(Locale.ROOT, "%-10s ops=%-7d err=%-3d thr=%10.1f/s p50=%8.3fms p95=%8.3fms p99=%8.3fms",
                operation, ops, errors, throughput, p50, p95, p99);
    }
}
