import com.sun.net.httpserver.{HttpExchange, HttpServer}
import java.net.InetSocketAddress
import java.nio.file.{Files, Paths}

object UiServer:

  private def env(name: String, default: String): String = sys.env.getOrElse(name, default)

  private def reply(ex: HttpExchange, status: Int, contentType: String, body: Array[Byte]): Unit =
    ex.getResponseHeaders.set("Content-Type", contentType)
    ex.sendResponseHeaders(status, body.length.toLong)
    ex.getResponseBody.write(body)
    ex.close()

  def main(args: Array[String]): Unit =
    val results = Paths.get(env("RESULTS_FILE", "results/results.json"))
    val page = getClass.getResourceAsStream("/index.html").readAllBytes()
    val server = HttpServer.create(InetSocketAddress(env("UI_PORT", "20380").toInt), 0)
    server.createContext("/api/results", ex =>
      if Files.exists(results) then reply(ex, 200, "application/json", Files.readAllBytes(results))
      else reply(ex, 404, "application/json", """{"error":"results.json not found, run ./scripts/test-all.sh"}""".getBytes("UTF-8"))
    )
    server.createContext("/", ex =>
      if ex.getRequestURI.getPath == "/" then reply(ex, 200, "text/html; charset=utf-8", page)
      else reply(ex, 404, "text/plain", "not found".getBytes("UTF-8"))
    )
    server.start()
    println(s"ui listening on http://localhost:${server.getAddress.getPort}")
