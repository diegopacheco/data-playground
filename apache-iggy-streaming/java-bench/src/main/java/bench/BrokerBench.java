package bench;

public interface BrokerBench {

    record ProducerOutcome(long sent, long sendErrors, long startedAtUs, long finishedAtUs) {
    }

    record Outcome(ProducerOutcome producer, Recorder recorder) {
    }

    Outcome run(BenchConfig cfg) throws Exception;

    static void drain(Recorder recorder, long sent, double seconds) throws InterruptedException {
        long deadline = System.nanoTime() + (long) (seconds * 1_000_000_000L);
        while (recorder.received() < sent && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }
    }

    static void pause() {
        try {
            Thread.sleep(0, 200_000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }
}
