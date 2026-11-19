package com.github.diegopacheco.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.Test;

class ProductionRunTest {

    @Test
    void stopWaitsForEveryInFlightSendSoTheAckedCountIsFinal() throws Exception {
        Set<String> delivered = ConcurrentHashMap.newKeySet();
        ProductionRun run = new ProductionRun("slow", 500, order -> {
            Thread.sleep(300);
            delivered.add(order.key());
        });
        run.start();
        Thread.sleep(400);
        RunStats stats = run.stop(Duration.ofSeconds(10));
        assertFalse(stats.running());
        assertTrue(stats.sent() > 0);
        assertEquals(stats.sent(), stats.acked());
        assertEquals(stats.acked(), delivered.size());
        assertEquals(0, stats.failed());
    }

    @Test
    void failedSendsAreCountedAndNeverReportedAsAcked() throws Exception {
        ProductionRun run = new ProductionRun("flaky", 200, order -> {
            if (order.seq() % 2 == 0) {
                throw new IllegalStateException("broker down");
            }
        });
        run.start();
        Thread.sleep(300);
        RunStats stats = run.stop(Duration.ofSeconds(5));
        assertEquals(stats.sent(), stats.acked() + stats.failed());
        assertTrue(stats.failed() > 0);
        assertTrue(stats.lastError().contains("broker down"));
    }

    @Test
    void rateIsHonouredSoTheRunSpansTheWholeBrokerRoll() throws Exception {
        ProductionRun run = new ProductionRun("paced", 100, order -> { });
        run.start();
        Thread.sleep(1_000);
        RunStats stats = run.stop(Duration.ofSeconds(5));
        assertTrue(stats.sent() >= 80 && stats.sent() <= 120, "sent " + stats.sent());
    }
}
