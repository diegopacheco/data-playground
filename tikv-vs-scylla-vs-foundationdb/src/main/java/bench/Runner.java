package bench;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntPredicate;

public final class Runner {

    public record Sample(long[] latencies, int errors, long wallNanos) {
    }

    private Runner() {
    }

    public static Sample run(int count, int threads, IntPredicate task) throws InterruptedException {
        long[] latencies = new long[count];
        AtomicInteger next = new AtomicInteger();
        AtomicInteger errors = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        long start = System.nanoTime();
        for (int t = 0; t < threads; t++) {
            pool.execute(() -> {
                for (int i = next.getAndIncrement(); i < count; i = next.getAndIncrement()) {
                    long begin = System.nanoTime();
                    boolean ok;
                    try {
                        ok = task.test(i);
                    } catch (RuntimeException e) {
                        ok = false;
                    }
                    latencies[i] = System.nanoTime() - begin;
                    if (!ok) errors.incrementAndGet();
                }
            });
        }
        pool.shutdown();
        if (!pool.awaitTermination(1, TimeUnit.HOURS)) throw new IllegalStateException("run did not finish");
        return new Sample(latencies, errors.get(), System.nanoTime() - start);
    }
}
