package com.github.diegopacheco.pipelinelag;

import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class RunRegistry {

    private static final Pattern RUN_ID = Pattern.compile("[A-Za-z0-9-]{1,64}");
    private static final int MAX_RATE = 2000;
    private static final Duration STOP_TIMEOUT = Duration.ofMinutes(2);

    private final OrderSender sender;
    private final Clock clock;
    private final Map<String, ProductionRun> runs = new ConcurrentHashMap<>();

    @Autowired
    public RunRegistry(OrderSender sender) {
        this(sender, Clock.systemUTC());
    }

    public RunRegistry(OrderSender sender, Clock clock) {
        this.sender = sender;
        this.clock = clock;
    }

    public Optional<RunStats> start(String runId, int ratePerSecond) {
        if (!RUN_ID.matcher(runId).matches()) {
            throw new IllegalArgumentException("runId must match " + RUN_ID.pattern());
        }
        if (ratePerSecond < 1 || ratePerSecond > MAX_RATE) {
            throw new IllegalArgumentException("rate must be between 1 and " + MAX_RATE);
        }
        ProductionRun run = new ProductionRun(runId, ratePerSecond, sender, clock);
        if (runs.putIfAbsent(runId, run) != null) {
            return Optional.empty();
        }
        run.start();
        return Optional.of(run.stats());
    }

    public Optional<RunStats> stats(String runId) {
        return Optional.ofNullable(runs.get(runId)).map(ProductionRun::stats);
    }

    public List<RunStats> all() {
        return runs.values().stream().map(ProductionRun::stats).toList();
    }

    public Optional<RunStats> stop(String runId) throws InterruptedException {
        ProductionRun run = runs.get(runId);
        if (run == null) {
            return Optional.empty();
        }
        return Optional.of(run.stop(STOP_TIMEOUT));
    }
}
