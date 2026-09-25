import com.datastax.oss.driver.api.core.CqlSession
import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.InetSocketAddress
import scala.jdk.CollectionConverters.*

object UiServer:

  private def env(name: String, default: String): String = sys.env.getOrElse(name, default)

  private def quote(s: String): String = "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

  def revenueJson(session: CqlSession): String =
    session
      .execute("SELECT category, total_orders, total_quantity, total_revenue FROM sales.revenue_by_category")
      .all()
      .asScala
      .sortBy(_.getString("category"))
      .map { r =>
        s"""{"category":${quote(r.getString("category"))},"total_orders":${r.getLong("total_orders")},"total_quantity":${r.getLong("total_quantity")},"total_revenue":${r.getDouble("total_revenue")}}"""
      }
      .mkString("[", ",", "]")

  private def reply(ex: HttpExchange, status: Int, contentType: String, body: Array[Byte]): Unit =
    ex.getResponseHeaders.set("Content-Type", contentType)
    ex.sendResponseHeaders(status, body.length.toLong)
    ex.getResponseBody.write(body)
    ex.close()

  def main(args: Array[String]): Unit =
    val session = CqlSession.builder()
      .addContactPoint(InetSocketAddress(env("CASSANDRA_HOST", "localhost"), env("CASSANDRA_PORT", "16042").toInt))
      .withLocalDatacenter("datacenter1")
      .build()
    val page = getClass.getResourceAsStream("/index.html").readAllBytes()
    val server = HttpServer.create(InetSocketAddress(env("UI_PORT", "16080").toInt), 0)
    server.createContext("/api/revenue", ex =>
      try reply(ex, 200, "application/json", revenueJson(session).getBytes("UTF-8"))
      catch case e: Exception => reply(ex, 500, "application/json", s"""{"error":${quote(String.valueOf(e.getMessage))}}""".getBytes("UTF-8"))
    )
    server.createContext("/", ex =>
      if ex.getRequestURI.getPath == "/" then reply(ex, 200, "text/html; charset=utf-8", page)
      else reply(ex, 404, "text/plain", "not found".getBytes("UTF-8"))
    )
    server.start()
    println(s"ui listening on http://localhost:${server.getAddress.getPort}")
