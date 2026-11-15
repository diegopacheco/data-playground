package com.github.diegopacheco.pipelinelag;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.Test;

class ProductionRunTest {

    @Test
    void eventTimeIsTakenWhenTheOrderIsCreatedNotWhenTheBrokerAcksSoLagIncludesTheSend() throws Exception {
        List<Long> stampedBeforeSend = new CopyOnWriteArrayList<>();
        ProductionRun run = new ProductionRun("stamp", 50, order -> {
            long before = System.currentTimeMillis();
            Thread.sleep(200);
            assertTrue(order.eventTimeMs() <= before);
            stampedBeforeSend.add(order.eventTimeMs());
        }, Clock.systemUTC());
        run.start();
        Thread.sleep(300);
        RunStats stats = run.stop(Duration.ofSeconds(5));
        assertEquals(stats.sent(), stats.acked());
        assertEquals(stats.acked(), stampedBeforeSend.size());
    }

    @Test
    void failedSendsAreCountedAndNeverReportedAsAcked() throws Exception {
        ProductionRun run = new ProductionRun("flaky", 200, order -> {
            if (order.seq() % 2 == 0) {
                throw new IllegalStateException("broker down");
            }
        }, Clock.systemUTC());
        run.start();
        Thread.sleep(300);
        RunStats stats = run.stop(Duration.ofSeconds(5));
        assertEquals(stats.sent(), stats.acked() + stats.failed());
        assertTrue(stats.failed() > 0);
        assertTrue(stats.lastError().contains("broker down"));
    }

    @Test
    void rateIsHonouredSoTheSloWindowSeesASteadyFlow() throws Exception {
        ProductionRun run = new ProductionRun("paced", 100, order -> { }, Clock.systemUTC());
        run.start();
        Thread.sleep(1_000);
        RunStats stats = run.stop(Duration.ofSeconds(5));
        assertTrue(stats.sent() >= 80 && stats.sent() <= 120, "sent " + stats.sent());
    }
}
