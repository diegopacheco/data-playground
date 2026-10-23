import java.net.URI
import java.net.http.{HttpClient, HttpRequest, HttpResponse}
import java.util.Base64

object PolarisApi:

  private val http = HttpClient.newHttpClient()
  private val base = Model.env("POLARIS_URL", "http://localhost:20902")
  private val catalog = "i9_catalog"
  private val tokenPattern = "\"access_token\"\\s*:\\s*\"([^\"]+)\"".r

  private def send(request: HttpRequest): String =
    val response = http.send(request, HttpResponse.BodyHandlers.ofString())
    if response.statusCode() / 100 != 2 then
      throw RuntimeException(s"polaris ${request.uri()} returned ${response.statusCode()}: ${response.body()}")
    response.body()

  def token(credential: String): String =
    val basic = Base64.getEncoder.encodeToString(credential.getBytes("UTF-8"))
    val body = send(
      HttpRequest.newBuilder(URI.create(s"$base/api/catalog/v1/oauth/tokens"))
        .header("Authorization", s"Basic $basic")
        .header("Content-Type", "application/x-www-form-urlencoded")
        .POST(HttpRequest.BodyPublishers.ofString("grant_type=client_credentials&scope=PRINCIPAL_ROLE:ALL"))
        .build()
    )
    tokenPattern.findFirstMatchIn(body).map(_.group(1)).getOrElse(throw RuntimeException("no access_token from polaris"))

  private def get(path: String, bearer: String): String =
    send(HttpRequest.newBuilder(URI.create(base + path)).header("Authorization", s"Bearer $bearer").GET().build())

  def overview(): String =
    val root = token(Model.env("ROOT_CREDENTIAL", "root:i9s3cr3t"))
    val engine = token(Model.env("POLARIS_CREDENTIAL", ""))
    val mgmt = "/api/management/v1"
    val parts = Seq(
      "catalogs" -> get(s"$mgmt/catalogs", root),
      "principals" -> get(s"$mgmt/principals", root),
      "principalRoles" -> get(s"$mgmt/principals/i9_engine/principal-roles", root),
      "catalogRoles" -> get(s"$mgmt/principal-roles/i9_engine_role/catalog-roles/$catalog", root),
      "grants" -> get(s"$mgmt/catalogs/$catalog/catalog-roles/i9_catalog_rw/grants", root),
      "namespaces" -> get(s"/api/catalog/v1/$catalog/namespaces", engine),
      "tables" -> get(s"/api/catalog/v1/$catalog/namespaces/sales/tables", engine)
    )
    parts.map((k, v) => s"${Json.quote(k)}:$v").mkString("{", ",", "}")
