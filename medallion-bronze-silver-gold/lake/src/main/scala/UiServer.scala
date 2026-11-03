import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.InetSocketAddress
import org.apache.spark.sql.{DataFrame, SparkSession}

object UiServer:

  private val maxSafeJsInteger = 9007199254740991L

  private def quote(s: String): String = "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

  private def jsonValue(v: Any): String = v match
    case null => "null"
    case s: String => quote(s)
    case d: java.math.BigDecimal => d.toPlainString
    case l: java.lang.Long if math.abs(l.longValue) > maxSafeJsInteger => quote(l.toString)
    case n: Number => n.toString
    case b: Boolean => b.toString
    case o => quote(o.toString)

  def toJson(df: DataFrame): String =
    val names = df.columns
    df.collect()
      .map(r => names.indices.map(i => s"${quote(names(i))}:${jsonValue(r.get(i))}").mkString("{", ",", "}"))
      .mkString("[", ",", "]")

  private def param(ex: HttpExchange, name: String, default: String): String =
    Option(ex.getRequestURI.getQuery).toSeq
      .flatMap(_.split("&"))
      .map(_.split("=", 2))
      .collectFirst { case Array(k, v) if k == name => v }
      .getOrElse(default)

  private def goldJson(spark: SparkSession, name: String): String =
    val table = Lake.gold.find(_.endsWith("." + name)).getOrElse(throw IllegalArgumentException(s"unknown gold table $name"))
    s"""{"table":${quote(name)},"rows":${toJson(Queries.gold(spark, table))}}"""

  private def quarantineJson(spark: SparkSession): String =
    s"""{"reasons":${toJson(Queries.quarantineReasons(spark))},"rows":${toJson(Queries.quarantineRows(spark))}}"""

  private def reply(ex: HttpExchange, status: Int, contentType: String, body: Array[Byte]): Unit =
    ex.getResponseHeaders.set("Content-Type", contentType)
    ex.sendResponseHeaders(status, body.length.toLong)
    ex.getResponseBody.write(body)
    ex.close()

  private def api(server: HttpServer, path: String, handler: HttpExchange => String): Unit =
    server.createContext(path, ex =>
      try reply(ex, 200, "application/json", handler(ex).getBytes("UTF-8"))
      catch case e: Exception => reply(ex, 500, "application/json", s"""{"error":${quote(String.valueOf(e.getMessage))}}""".getBytes("UTF-8"))
    )

  def main(args: Array[String]): Unit =
    val spark = Lake.session("medallion-lake-ui")
    val page = getClass.getResourceAsStream("/index.html").readAllBytes()
    val server = HttpServer.create(InetSocketAddress(sys.env.getOrElse("UI_PORT", "25080").toInt), 0)
    api(server, "/api/layers", _ => toJson(Queries.layers(spark)))
    api(server, "/api/bronze", _ => toJson(Queries.bronzeFiles(spark)))
    api(server, "/api/quarantine", _ => quarantineJson(spark))
    api(server, "/api/silver/late", _ => toJson(Queries.silverFromLaterFiles(spark)))
    api(server, "/api/gold", ex => goldJson(spark, param(ex, "table", "revenue_by_category")))
    server.createContext("/", ex =>
      if ex.getRequestURI.getPath == "/" then reply(ex, 200, "text/html; charset=utf-8", page)
      else reply(ex, 404, "text/plain", "not found".getBytes("UTF-8"))
    )
    server.start()
    println(s"ui listening on http://localhost:${server.getAddress.getPort}")
