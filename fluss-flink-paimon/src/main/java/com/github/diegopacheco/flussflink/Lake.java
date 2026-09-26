package com.github.diegopacheco.flussflink;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.types.Row;
import org.apache.flink.util.CloseableIterator;

import java.util.ArrayList;
import java.util.List;

public final class Lake {

    private final TableEnvironment env;

    public Lake() {
        env = TableEnvironment.create(EnvironmentSettings.newInstance().inBatchMode().withConfiguration(Settings.localCluster()).build());
        env.executeSql("CREATE CATALOG fluss_catalog WITH ('type' = 'fluss', 'bootstrap.servers' = '" + Settings.BOOTSTRAP + "')");
        env.executeSql("CREATE CATALOG paimon_catalog WITH ('type' = 'paimon', 'warehouse' = '" + Settings.WAREHOUSE + "')");
        env.executeSql("USE CATALOG fluss_catalog");
        env.executeSql("USE " + Settings.DATABASE);
    }

    public List<Order> union() throws Exception {
        return orders("SELECT " + Order.COLUMNS + " FROM " + Settings.TABLE + " ORDER BY order_id");
    }

    public List<Order> lake() throws Exception {
        return orders("SELECT " + Order.COLUMNS + " FROM `" + Settings.TABLE + "$lake` ORDER BY order_id");
    }

    public List<Order> lakeLookup(int id) throws Exception {
        return orders("SELECT " + Order.COLUMNS + " FROM `" + Settings.TABLE + "$lake` WHERE order_id = " + id);
    }

    public List<Row> snapshots() throws Exception {
        return query("SELECT snapshot_id, commit_kind, CAST(commit_time AS STRING), total_record_count, delta_record_count FROM `"
                + Settings.TABLE + "$lake$snapshots` ORDER BY snapshot_id DESC");
    }

    public void dropLakeTable() {
        env.executeSql("DROP TABLE IF EXISTS paimon_catalog." + Settings.DATABASE + "." + Settings.TABLE);
    }

    private List<Order> orders(String sql) throws Exception {
        return query(sql).stream().map(Order::fromFlink).toList();
    }

    public List<Row> query(String sql) throws Exception {
        List<Row> rows = new ArrayList<>();
        try (CloseableIterator<Row> it = env.executeSql(sql).collect()) {
            it.forEachRemaining(rows::add);
        }
        return rows;
    }
}
