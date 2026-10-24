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
    case l: java.lang.Long if math.abs(l.longValue) >maxSafeJsInteger => quote(l.toString)
    case n: Number => n.toString
    case b: Boolean => b.toString
    case o => quote(o.toString)

  def toJson(df: DataFrame): String =
    val names = df.columns
    df.collect()
      .map(r => names.indices.map(i => s"${quote(names(i))}:${jsonValue(r.get(i))}").mkString("{", ",", "}"))
      .mkString("[", ",", "]")

  def snapshotId(spark: SparkSession, which: String): Long =
    val ids = Lake.snapshots(spark).collect().map(_.getAs[Long]("snapshot_id"))
    which match
      case "first" => ids.head
      case "latest" => ids.last
      case id => id.toLong

  def schemaJson(spark: SparkSession): String =
    spark.table(Lake.table).schema.fields
      .map(f => s"""{"name":${quote(f.name)},"type":${quote(f.dataType.simpleString)}}""")
      .mkString("[", ",", "]")

  def revenueJson(spark: SparkSession, which: String): String =
    val id = snapshotId(spark, which)
    s"""{"snapshot_id":${quote(id.toString)},"rows":${toJson(Lake.revenueAt(spark, id))}}"""

  private def param(ex: HttpExchange, name: String, default: String): String =
    Option(ex.getRequestURI.getQuery).toSeq
      .flatMap(_.split("&"))
      .map(_.split("=", 2))
      .collectFirst { case Array(k, v) if k == name => v }
      .getOrElse(default)

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
    val spark = Lake.session("iceberg-lake-ui")
    val page = getClass.getResourceAsStream("/index.html").readAllBytes()
    val server = HttpServer.create(InetSocketAddress(sys.env.getOrElse("UI_PORT", "20180").toInt), 0)
    api(server, "/api/snapshots", _ => toJson(Lake.snapshots(spark)))
    api(server, "/api/schema", _ => schemaJson(spark))
    api(server, "/api/revenue", ex => revenueJson(spark, param(ex, "snapshot", "latest")))
    server.createContext("/", ex =>
      if ex.getRequestURI.getPath == "/" then reply(ex, 200, "text/html; charset=utf-8", page)
      else reply(ex, 404, "text/plain", "not found".getBytes("UTF-8"))
    )
    server.start()
    println(s"ui listening on http://localhost:${server.getAddress.getPort}")
