package beam;

public final class Env {

  private Env() {
  }

  public static String get(String name, String fallback) {
    String value = System.getenv(name);
    return value == null || value.isBlank() ? fallback : value;
  }

  public static String jdbcUrl() {
    return get("JDBC_URL", "jdbc:postgresql://localhost:26132/sales");
  }

  public static String jdbcUser() {
    return get("JDBC_USER", "beam");
  }

  public static String jdbcPassword() {
    return get("JDBC_PASSWORD", "beam");
  }
}
