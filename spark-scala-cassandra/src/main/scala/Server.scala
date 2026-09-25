import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.InetSocketAddress
import java.nio.charset.StandardCharsets
import scala.jdk.CollectionConverters.*
import scala.util.Using

object Server:
  lazy val session = Cassandra.session()

  def quote(s: String): String =
    "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

  def revenueJson(): String =
    val rows = session
      .execute(s"SELECT category, total_orders, total_quantity, total_revenue FROM ${Cassandra.keyspace}.${Cassandra.table}")
      .all()
      .asScala
      .sortBy(r => -r.getDouble("total_revenue"))
      .map { r =>
        s"""{"category":${quote(r.getString("category"))},"total_orders":${r.getLong("total_orders")},"total_quantity":${r.getLong("total_quantity")},"total_revenue":${r.getDouble("total_revenue")}}"""
      }
    rows.mkString("[", ",", "]")

  def indexHtml(): String =
    Using.resource(getClass.getResourceAsStream("/index.html"))(in => String(in.readAllBytes(), StandardCharsets.UTF_8))

  def send(exchange: HttpExchange, status: Int, contentType: String, body: String): Unit =
    val bytes = body.getBytes(StandardCharsets.UTF_8)
    exchange.getResponseHeaders.set("Content-Type", contentType)
    exchange.sendResponseHeaders(status, bytes.length)
    Using.resource(exchange.getResponseBody)(_.write(bytes))

  def handle(exchange: HttpExchange): Unit =
    try
      exchange.getRequestURI.getPath match
        case "/api/revenue" => send(exchange, 200, "application/json", revenueJson())
        case "/" | "/index.html" => send(exchange, 200, "text/html; charset=utf-8", indexHtml())
        case _ => send(exchange, 404, "text/plain", "not found")
    catch
      case e: Exception => send(exchange, 500, "application/json", s"""{"error":${quote(String.valueOf(e.getMessage))}}""")

  def main(args: Array[String]): Unit =
    val port = sys.env.getOrElse("UI_PORT", "11080").toInt
    val server = HttpServer.create(InetSocketAddress(port), 0)
    server.createContext("/", exchange => handle(exchange))
    server.start()
    println(s"ui listening on http://localhost:$port")
