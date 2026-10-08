package sales;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

public final class MySqlStore {

    private static final String[] CATEGORIES = {"books", "clothing", "electronics", "home", "sports", "toys"};
    private static final int FIRST_UI_ID = 9000;

    public List<Totals> totals() throws SQLException {
        List<Totals> result = new ArrayList<>();
        try (Connection c = connect(); Statement s = c.createStatement();
             ResultSet rs = s.executeQuery("SELECT category, COUNT(*), SUM(quantity), SUM(quantity * price) FROM orders GROUP BY category")) {
            while (rs.next()) {
                result.add(new Totals(rs.getString(1), rs.getLong(2), rs.getLong(3), rs.getBigDecimal(4)));
            }
        }
        return result;
    }

    public long orderCount() throws SQLException {
        try (Connection c = connect(); Statement s = c.createStatement(); ResultSet rs = s.executeQuery("SELECT COUNT(*) FROM orders")) {
            rs.next();
            return rs.getLong(1);
        }
    }

    public String insert() throws SQLException {
        try (Connection c = connect()) {
            int id = Math.max(FIRST_UI_ID, maxId(c)) + 1;
            try (PreparedStatement p = c.prepareStatement("INSERT INTO orders VALUES (?, 'UI Shopper', 'Gift Card', ?, ?, 25.00, '2026-02-01T12:00:00Z')")) {
                p.setInt(1, id);
                p.setString(2, CATEGORIES[id % CATEGORIES.length]);
                p.setInt(3, 1 + id % 3);
                p.executeUpdate();
            }
            return "inserted order " + id;
        }
    }

    public String update() throws SQLException {
        try (Connection c = connect()) {
            int id = maxId(c);
            if (id <= FIRST_UI_ID) {
                return "no UI order to update, insert one first";
            }
            try (PreparedStatement p = c.prepareStatement("UPDATE orders SET quantity = quantity + 1, category = ? WHERE order_id = ?")) {
                p.setString(1, CATEGORIES[(id + 1) % CATEGORIES.length]);
                p.setInt(2, id);
                p.executeUpdate();
            }
            return "updated order " + id + " quantity + 1 and moved to " + CATEGORIES[(id + 1) % CATEGORIES.length];
        }
    }

    public String delete() throws SQLException {
        try (Connection c = connect()) {
            int id = maxId(c);
            if (id <= FIRST_UI_ID) {
                return "no UI order to delete, insert one first";
            }
            try (PreparedStatement p = c.prepareStatement("DELETE FROM orders WHERE order_id = ?")) {
                p.setInt(1, id);
                p.executeUpdate();
            }
            return "deleted order " + id;
        }
    }

    private int maxId(Connection c) throws SQLException {
        try (Statement s = c.createStatement(); ResultSet rs = s.executeQuery("SELECT COALESCE(MAX(order_id), 0) FROM orders")) {
            rs.next();
            return rs.getInt(1);
        }
    }

    private Connection connect() throws SQLException {
        return DriverManager.getConnection(Settings.MYSQL_URL);
    }
}
