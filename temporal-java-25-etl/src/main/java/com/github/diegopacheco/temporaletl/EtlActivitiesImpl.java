package com.github.diegopacheco.temporaletl;

import com.github.diegopacheco.temporaletl.Model.CategoryTotal;
import com.github.diegopacheco.temporaletl.Model.Checkpoint;
import com.github.diegopacheco.temporaletl.Model.ExtractResult;
import com.github.diegopacheco.temporaletl.Model.Order;
import com.github.diegopacheco.temporaletl.Model.TransformResult;
import io.temporal.activity.Activity;
import io.temporal.failure.ApplicationFailure;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class EtlActivitiesImpl implements EtlActivities {

    @Override
    public ExtractResult extractOrders(String csvPath, int failAttempts) {
        var info = Activity.getExecutionContext().getInfo();
        int attempt = info.getAttempt();
        log("extractOrders workflow=%s attempt=%d", info.getWorkflowId(), attempt);
        if (attempt <= failAttempts) {
            throw ApplicationFailure.newFailure("source unavailable on attempt " + attempt, "SourceUnavailable");
        }
        try (var lines = Files.lines(Path.of(csvPath))) {
            var orders = lines.skip(1).filter(l -> !l.isBlank()).map(EtlActivitiesImpl::parse).toList();
            log("extractOrders workflow=%s attempt=%d orders=%d", info.getWorkflowId(), attempt, orders.size());
            return new ExtractResult(orders, attempt);
        } catch (IOException e) {
            throw Activity.wrap(e);
        }
    }

    @Override
    public TransformResult transformAggregate(List<Order> orders, int millisPerOrder) {
        var ctx = Activity.getExecutionContext();
        var info = ctx.getInfo();
        var checkpoint = ctx.getHeartbeatDetails(Checkpoint.class).orElse(new Checkpoint(0, List.of()));
        Map<String, CategoryTotal> totals = new TreeMap<>();
        checkpoint.totals().forEach(t -> totals.put(t.category(), t));
        log("transformAggregate workflow=%s attempt=%d resumedFrom=%d", info.getWorkflowId(), info.getAttempt(), checkpoint.next());
        for (int i = checkpoint.next(); i < orders.size(); i++) {
            var order = orders.get(i);
            totals.merge(order.category(), new CategoryTotal(order.category(), 0, 0, 0).add(order), (a, b) -> a.add(order));
            sleep(millisPerOrder);
            ctx.heartbeat(new Checkpoint(i + 1, List.copyOf(totals.values())));
            if ((i + 1) % 10 == 0) {
                log("transformAggregate workflow=%s attempt=%d progress=%d/%d", info.getWorkflowId(), info.getAttempt(), i + 1, orders.size());
            }
        }
        return new TransformResult(List.copyOf(totals.values()), checkpoint.next(), info.getAttempt());
    }

    @Override
    public int loadToPostgres(String workflowId, List<CategoryTotal> totals) {
        try {
            int rows = Db.upsert(workflowId, totals);
            log("loadToPostgres workflow=%s rows=%d", workflowId, rows);
            return rows;
        } catch (SQLException e) {
            throw Activity.wrap(e);
        }
    }

    private static Order parse(String line) {
        var f = line.split(",");
        long cents = new BigDecimal(f[5].trim()).movePointRight(2).longValueExact();
        return new Order(Long.parseLong(f[0].trim()), f[1], f[2], f[3], Integer.parseInt(f[4].trim()), cents);
    }

    private static void sleep(int millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw Activity.wrap(e);
        }
    }

    private static void log(String format, Object... args) {
        System.out.println(String.format(format, args));
    }
}
