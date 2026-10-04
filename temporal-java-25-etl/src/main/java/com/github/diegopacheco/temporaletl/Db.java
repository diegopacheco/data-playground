package com.github.diegopacheco.temporaletl;

import com.github.diegopacheco.temporaletl.Model.CategoryTotal;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class Db {

    private static final String CREATE = """
            CREATE TABLE IF NOT EXISTS revenue_by_category (
              category text PRIMARY KEY,
              total_orders bigint NOT NULL,
              total_quantity bigint NOT NULL,
              total_revenue numeric(14,2) NOT NULL,
              workflow_id text NOT NULL,
              updated_at timestamptz NOT NULL
            )""";

    private static final String UPSERT = """
            INSERT INTO revenue_by_category (category, total_orders, total_quantity, total_revenue, workflow_id, updated_at)
            VALUES (?, ?, ?, ?, ?, now())
            ON CONFLICT (category) DO UPDATE SET
              total_orders = EXCLUDED.total_orders,
              total_quantity = EXCLUDED.total_quantity,
              total_revenue = EXCLUDED.total_revenue,
              workflow_id = EXCLUDED.workflow_id,
              updated_at = EXCLUDED.updated_at""";

    private static final String SELECT = """
            SELECT category, total_orders, total_quantity, total_revenue, workflow_id, updated_at
            FROM revenue_by_category ORDER BY total_revenue DESC""";

    private Db() {
    }

    public static Connection connect() throws SQLException {
        return DriverManager.getConnection(Config.pgUrl(), Config.pgUser(), Config.pgPassword());
    }

    public static void init() throws SQLException {
        try (var conn = connect(); var st = conn.createStatement()) {
            st.execute(CREATE);
        }
    }

    public static int upsert(String workflowId, List<CategoryTotal> totals) throws SQLException {
        try (var conn = connect(); var ps = conn.prepareStatement(UPSERT)) {
            conn.setAutoCommit(false);
            for (var t : totals) {
                ps.setString(1, t.category());
                ps.setLong(2, t.orders());
                ps.setLong(3, t.quantity());
                ps.setBigDecimal(4, BigDecimal.valueOf(t.revenueCents(), 2));
                ps.setString(5, workflowId);
                ps.addBatch();
            }
            int rows = ps.executeBatch().length;
            conn.commit();
            return rows;
        }
    }

    public static List<Map<String, Object>> revenue() throws SQLException {
        var rows = new ArrayList<Map<String, Object>>();
        try (var conn = connect(); var st = conn.createStatement(); var rs = st.executeQuery(SELECT)) {
            while (rs.next()) {
                var row = new LinkedHashMap<String, Object>();
                row.put("category", rs.getString(1));
                row.put("total_orders", rs.getLong(2));
                row.put("total_quantity", rs.getLong(3));
                row.put("total_revenue", rs.getBigDecimal(4));
                row.put("workflow_id", rs.getString(5));
                row.put("updated_at", rs.getTimestamp(6).toInstant().toString());
                rows.add(row);
            }
        }
        return rows;
    }
}
