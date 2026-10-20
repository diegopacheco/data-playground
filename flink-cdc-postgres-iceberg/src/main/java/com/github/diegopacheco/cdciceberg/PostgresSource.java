package com.github.diegopacheco.cdciceberg;

import java.io.IOException;
import java.nio.file.Files;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class PostgresSource {

    private final Settings settings;

    public PostgresSource(Settings settings) {
        this.settings = settings;
    }

    public List<CategoryStats> categoryStats() throws SQLException {
        String sql = "SELECT category, COUNT(*), SUM(quantity), SUM(quantity * price) FROM orders GROUP BY category ORDER BY category";
        List<CategoryStats> result = new ArrayList<>();
        try (Connection c = connect(); Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) {
                result.add(new CategoryStats(rs.getString(1), rs.getLong(2), rs.getLong(3), rs.getBigDecimal(4)));
            }
        }
        return result;
    }

    public List<OrderRow> rows() throws SQLException {
        String sql = "SELECT order_id, customer, product, category, quantity, price, ts FROM orders";
        List<OrderRow> result = new ArrayList<>();
        try (Connection c = connect(); Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) {
                result.add(new OrderRow(rs.getInt(1), rs.getString(2), rs.getString(3), rs.getString(4),
                        rs.getInt(5), rs.getBigDecimal(6), rs.getObject(7, LocalDateTime.class)));
            }
        }
        return result;
    }

    public void runScript(String fileName) throws SQLException, IOException {
        String script = Files.readString(settings.sqlDir().resolve(fileName));
        try (Connection c = connect(); Statement s = c.createStatement()) {
            s.execute(script);
        }
    }

    private Connection connect() throws SQLException {
        return DriverManager.getConnection(settings.jdbcUrl(), settings.pgUser(), settings.pgPassword());
    }
}
