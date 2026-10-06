package bench;

import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntFunction;

public final class Runner {

    private Runner() {
    }

    public static Stats run(String operation, int count, int concurrency, IntFunction<CompletionStage<Boolean>> op) throws InterruptedException {
        long[] latencies = new long[count];
        AtomicInteger errors = new AtomicInteger();
        Semaphore permits = new Semaphore(concurrency);
        CountDownLatch done = new CountDownLatch(count);
        long start = System.nanoTime();
        for (int i = 0; i < count; i++) {
            permits.acquire();
            int index = i;
            long begin = System.nanoTime();
            op.apply(index).whenComplete((ok, error) -> {
                latencies[index] = System.nanoTime() - begin;
                if (error != null || !Boolean.TRUE.equals(ok)) errors.incrementAndGet();
                permits.release();
                done.countDown();
            });
        }
        done.await();
        return Stats.of(operation, latencies, errors.get(), System.nanoTime() - start);
    }
}
