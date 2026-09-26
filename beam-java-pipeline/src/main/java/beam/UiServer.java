package beam;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public class UiServer {

  static final String QUERY =
      "SELECT category, total_orders, total_quantity, total_revenue FROM revenue_by_category ORDER BY total_revenue DESC";

  static String quote(String s) {
    return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
  }

  static String revenueJson() throws SQLException {
    List<String> rows = new ArrayList<>();
    try (Connection c = DriverManager.getConnection(Env.jdbcUrl(), Env.jdbcUser(), Env.jdbcPassword());
         ResultSet rs = c.createStatement().executeQuery(QUERY)) {
      while (rs.next()) {
        rows.add("{\"category\":" + quote(rs.getString(1))
            + ",\"total_orders\":" + rs.getLong(2)
            + ",\"total_quantity\":" + rs.getLong(3)
            + ",\"total_revenue\":" + rs.getBigDecimal(4).toPlainString() + "}");
      }
    }
    return "[" + String.join(",", rows) + "]";
  }

  static void reply(HttpExchange ex, int status, String type, byte[] body) throws IOException {
    ex.getResponseHeaders().set("Content-Type", type);
    ex.sendResponseHeaders(status, body.length);
    ex.getResponseBody().write(body);
    ex.close();
  }

  public static void main(String[] args) throws IOException {
    byte[] page;
    try (InputStream in = UiServer.class.getResourceAsStream("/index.html")) {
      page = in.readAllBytes();
    }
    int port = Integer.parseInt(Env.get("UI_PORT", "26180"));
    HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
    server.createContext("/api/revenue", ex -> {
      try {
        reply(ex, 200, "application/json", revenueJson().getBytes(StandardCharsets.UTF_8));
      } catch (SQLException e) {
        reply(ex, 500, "application/json", ("{\"error\":" + quote(String.valueOf(e.getMessage())) + "}").getBytes(StandardCharsets.UTF_8));
      }
    });
    server.createContext("/", ex -> {
      if (ex.getRequestURI().getPath().equals("/")) {
        reply(ex, 200, "text/html; charset=utf-8", page);
      } else {
        reply(ex, 404, "text/plain", "not found".getBytes(StandardCharsets.UTF_8));
      }
    });
    server.start();
    System.out.println("ui listening on port " + port);
  }
}
