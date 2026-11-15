package com.github.diegopacheco.pipelinelag;

import java.time.Clock;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.LockSupport;

public final class ProductionRun {

    private final String runId;
    private final int ratePerSecond;
    private final OrderSender sender;
    private final Clock clock;
    private final AtomicLong sent = new AtomicLong();
    private final AtomicLong acked = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();
    private final ExecutorService deliveries = Executors.newVirtualThreadPerTaskExecutor();
    private final Thread pacer;
    private volatile boolean running = true;
    private volatile String lastError = "";

    public ProductionRun(String runId, int ratePerSecond, OrderSender sender, Clock clock) {
        this.runId = runId;
        this.ratePerSecond = ratePerSecond;
        this.sender = sender;
        this.clock = clock;
        this.pacer = Thread.ofVirtual().name("pacer-" + runId).unstarted(this::pace);
    }

    public void start() {
        pacer.start();
    }

    public RunStats stop(Duration timeout) throws InterruptedException {
        running = false;
        pacer.join();
        deliveries.shutdown();
        if (!deliveries.awaitTermination(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
            lastError = "deliveries still in flight after " + timeout;
        }
        return stats();
    }

    public RunStats stats() {
        return new RunStats(runId, ratePerSecond, sent.get(), acked.get(), failed.get(), running, lastError);
    }

    private void pace() {
        long interval = TimeUnit.SECONDS.toNanos(1) / ratePerSecond;
        long next = System.nanoTime();
        long seq = 0;
        while (running) {
            long current = seq++;
            sent.incrementAndGet();
            deliveries.submit(() -> deliver(Order.of(runId, current, clock.millis())));
            next += interval;
            LockSupport.parkNanos(next - System.nanoTime());
        }
    }

    private void deliver(Order order) {
        try {
            sender.send(order);
            acked.incrementAndGet();
        } catch (Exception e) {
            failed.incrementAndGet();
            lastError = e.toString();
        }
    }
}
