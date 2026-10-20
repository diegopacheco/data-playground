package com.github.diegopacheco.cdciceberg;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.types.Row;
import org.apache.flink.util.CloseableIterator;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Function;

public class IcebergSource {

    public record Snapshot(String snapshotId, String committedAt, String operation, Map<?, ?> summary) {
    }

    private final ExecutorService plannerThread = Executors.newSingleThreadExecutor();
    private final TableEnvironment tables;

    public IcebergSource(Settings settings) throws Exception {
        tables = plannerThread.submit(() -> {
            TableEnvironment env = TableEnvironment.create(EnvironmentSettings.newInstance()
                    .inBatchMode().withConfiguration(Settings.flinkPorts("READER")).build());
            env.getConfig().set("parallelism.default", "1");
            Lakehouse.registerCatalog(env, settings);
            return env;
        }).get();
    }

    public List<CategoryStats> categoryStats() throws Exception {
        String sql = "SELECT category, COUNT(*), SUM(quantity), SUM(CAST(quantity AS DECIMAL(10,0)) * price) FROM "
                + Lakehouse.TABLE + " GROUP BY category";
        return query(sql, r -> new CategoryStats((String) r.getField(0), ((Number) r.getField(1)).longValue(),
                ((Number) r.getField(2)).longValue(), (BigDecimal) r.getField(3)));
    }

    public List<OrderRow> rows() throws Exception {
        String sql = "SELECT order_id, customer, product, category, quantity, price, ts FROM " + Lakehouse.TABLE;
        return query(sql, r -> new OrderRow((Integer) r.getField(0), (String) r.getField(1), (String) r.getField(2),
                (String) r.getField(3), (Integer) r.getField(4), (BigDecimal) r.getField(5), (LocalDateTime) r.getField(6)));
    }

    public List<Snapshot> snapshots() throws Exception {
        String sql = "SELECT snapshot_id, committed_at, operation, summary FROM lake.shop.`orders$snapshots`";
        return query(sql, r -> new Snapshot(String.valueOf(r.getField(0)), String.valueOf(r.getField(1)),
                String.valueOf(r.getField(2)), (Map<?, ?>) r.getField(3)));
    }

    private <T> List<T> query(String sql, Function<Row, T> mapper) throws Exception {
        return plannerThread.submit(() -> {
            List<T> result = new ArrayList<>();
            try (CloseableIterator<Row> it = tables.executeSql(sql).collect()) {
                while (it.hasNext()) {
                    result.add(mapper.apply(it.next()));
                }
            }
            return result;
        }).get();
    }
}
