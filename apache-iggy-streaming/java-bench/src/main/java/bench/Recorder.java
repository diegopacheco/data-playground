package bench;

public final class Recorder {

    private final OrderTracker tracker;
    private final long granularityUs;
    private final Latencies latencies = new Latencies();
    private volatile long warmupUntilUs;
    private long tsChecked;
    private long tsViolations;
    private long minSentAtUs;
    private long maxSentAtUs;
    private long lastReceivedAtUs;

    public Recorder(int partitions, long warmupUntilUs, long brokerGranularityUs) {
        this.tracker = new OrderTracker(partitions);
        this.warmupUntilUs = warmupUntilUs;
        this.granularityUs = brokerGranularityUs;
    }

    public void warmupUntil(long micros) {
        this.warmupUntilUs = micros;
    }

    public synchronized void observe(int partition, byte[] data, long brokerTsUs, long receivedAtUs) {
        Payload.Stamp stamp = Payload.decode(data);
        tracker.observe(partition, stamp.seq());
        long sentFloor = stamp.sentAtUs() / granularityUs * granularityUs;
        tsChecked++;
        if (brokerTsUs < sentFloor || brokerTsUs > receivedAtUs) {
            tsViolations++;
        }
        if (minSentAtUs == 0 || stamp.sentAtUs() < minSentAtUs) {
            minSentAtUs = stamp.sentAtUs();
        }
        maxSentAtUs = Math.max(maxSentAtUs, stamp.sentAtUs());
        lastReceivedAtUs = Math.max(lastReceivedAtUs, receivedAtUs);
        if (stamp.sentAtUs() >= warmupUntilUs) {
            latencies.add(receivedAtUs - stamp.sentAtUs());
        }
    }

    public synchronized long received() {
        return tracker.received();
    }

    public OrderTracker tracker() {
        return tracker;
    }

    public Latencies latencies() {
        return latencies;
    }

    public long tsChecked() {
        return tsChecked;
    }

    public long tsViolations() {
        return tsViolations;
    }

    public long minSentAtUs() {
        return minSentAtUs;
    }

    public long maxSentAtUs() {
        return maxSentAtUs;
    }

    public long lastReceivedAtUs() {
        return lastReceivedAtUs;
    }
}
