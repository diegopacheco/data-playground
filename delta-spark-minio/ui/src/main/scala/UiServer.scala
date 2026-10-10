import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.InetSocketAddress
import java.nio.file.{Files, Path}

object UiServer:

  val reports = Set("versions", "history", "changes", "change_summary", "revenue", "vacuum")

  private def env(name: String, default: String): String = sys.env.getOrElse(name, default)

  private def reply(ex: HttpExchange, status: Int, contentType: String, body: Array[Byte]): Unit =
    ex.getResponseHeaders.set("Content-Type", contentType)
    ex.sendResponseHeaders(status, body.length.toLong)
    ex.getResponseBody.write(body)
    ex.close()

  private def api(ex: HttpExchange, dir: Path): Unit =
    val name = ex.getRequestURI.getPath.stripPrefix("/api/")
    val file = dir.resolve(s"$name.json")
    if !reports.contains(name) then reply(ex, 404, "application/json", """{"error":"unknown report"}""".getBytes("UTF-8"))
    else if !Files.exists(file) then reply(ex, 404, "application/json", """{"error":"run ./scripts/pipeline.sh first"}""".getBytes("UTF-8"))
    else reply(ex, 200, "application/json", Files.readAllBytes(file))

  def main(args: Array[String]): Unit =
    val dir = Path.of(env("OUTPUT_DIR", "output"))
    val page = getClass.getResourceAsStream("/index.html").readAllBytes()
    val server = HttpServer.create(InetSocketAddress(env("UI_PORT", "20280").toInt), 0)
    server.createContext("/api/", ex => api(ex, dir))
    server.createContext("/", ex =>
      if ex.getRequestURI.getPath == "/" then reply(ex, 200, "text/html; charset=utf-8", page)
      else reply(ex, 404, "text/plain", "not found".getBytes("UTF-8"))
    )
    server.start()
    println(s"ui listening on http://localhost:${server.getAddress.getPort}")
