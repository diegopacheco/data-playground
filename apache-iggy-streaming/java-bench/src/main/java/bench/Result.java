package bench;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public final class Result {

    private Result() {
    }

    public static Map<String, Object> build(BenchConfig cfg, BrokerBench.Outcome outcome, long finishedAtUs) {
        BrokerBench.ProducerOutcome producer = outcome.producer();
        Recorder recorder = outcome.recorder();
        OrderTracker tracker = recorder.tracker();
        double activeS = Math.max(recorder.lastReceivedAtUs() - producer.startedAtUs(), 1) / 1_000_000.0;
        double sendS = Math.max(producer.finishedAtUs() - producer.startedAtUs(), 1) / 1_000_000.0;
        double consumeRate = recorder.received() / activeS;
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("broker", cfg.broker());
        out.put("client", "java");
        out.put("rate", cfg.rate());
        out.put("size", cfg.size());
        out.put("seconds", cfg.seconds());
        out.put("partitions", cfg.partitions());
        out.put("sent", producer.sent());
        out.put("received", recorder.received());
        out.put("send_errors", producer.sendErrors());
        out.put("gaps", tracker.gaps());
        out.put("backwards", tracker.backwards());
        out.put("misrouted", tracker.misrouted());
        out.put("in_order", tracker.inOrder());
        out.put("complete", tracker.complete(producer.sent()));
        out.put("send_rate", round(producer.sent() / sendS, 1));
        out.put("consume_rate", round(consumeRate, 1));
        out.put("mb_per_s", round(consumeRate * cfg.size() / 1_000_000.0, 3));
        out.put("latency", recorder.latencies().size() == 0 ? null : latency(recorder.latencies().summarize()));
        out.put("ts_checked", recorder.tsChecked());
        out.put("ts_violations", recorder.tsViolations());
        out.put("run_started_us", producer.startedAtUs());
        out.put("run_finished_us", finishedAtUs);
        out.put("min_sent_at_us", recorder.minSentAtUs());
        out.put("max_sent_at_us", recorder.maxSentAtUs());
        return out;
    }

    private static Map<String, Object> latency(Latencies.Summary s) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("samples", s.samples());
        out.put("p50_ms", s.p50Ms());
        out.put("p95_ms", s.p95Ms());
        out.put("p99_ms", s.p99Ms());
        out.put("max_ms", s.maxMs());
        return out;
    }

    private static double round(double value, int digits) {
        double scale = Math.pow(10, digits);
        return Math.round(value * scale) / scale;
    }

    public static String toJson(Object value) {
        return switch (value) {
            case null -> "null";
            case String s -> "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
            case Map<?, ?> m -> m.entrySet().stream()
                    .map(e -> toJson(String.valueOf(e.getKey())) + ":" + toJson(e.getValue()))
                    .collect(Collectors.joining(",", "{", "}"));
            default -> String.valueOf(value);
        };
    }

    public static String render(Map<String, Object> result) {
        return "RESULT " + toJson(result);
    }
}
