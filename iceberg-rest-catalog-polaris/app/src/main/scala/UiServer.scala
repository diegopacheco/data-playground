import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.InetSocketAddress

object UiServer:

  private def reply(ex: HttpExchange, status: Int, contentType: String, body: Array[Byte]): Unit =
    ex.getResponseHeaders.set("Content-Type", contentType)
    ex.sendResponseHeaders(status, body.length.toLong)
    ex.getResponseBody.write(body)
    ex.close()

  private def api(server: HttpServer, path: String, handler: () => String): Unit =
    server.createContext(path, ex =>
      try reply(ex, 200, "application/json", handler().getBytes("UTF-8"))
      catch case e: Exception => reply(ex, 500, "application/json", s"""{"error":${Json.quote(String.valueOf(e.getMessage))}}""".getBytes("UTF-8"))
    )

  def main(args: Array[String]): Unit =
    val spark = SparkLake.session("polaris-ui")
    val page = getClass.getResourceAsStream("/index.html").readAllBytes()
    val server = HttpServer.create(InetSocketAddress(Model.env("UI_PORT", "20980").toInt), 0)
    api(server, "/api/spark/aggregates", () => Json.aggregates(SparkLake.aggregates(spark)))
    api(server, "/api/trino/aggregates", () => Json.aggregates(TrinoLake.aggregates()))
    api(server, "/api/spark/trino-rows", () => Json.frame(SparkLake.ordersFrom(spark, Model.trinoFirstId)))
    api(server, "/api/snapshots", () => Json.frame(SparkLake.snapshots(spark)))
    api(server, "/api/polaris", () => PolarisApi.overview())
    server.createContext("/", ex =>
      if ex.getRequestURI.getPath == "/" then reply(ex, 200, "text/html; charset=utf-8", page)
      else reply(ex, 404, "text/plain", "not found".getBytes("UTF-8"))
    )
    server.start()
    println(s"ui listening on http://localhost:${server.getAddress.getPort}")
