import com.datastax.oss.driver.api.core.CqlSession
import java.net.InetSocketAddress

object Cassandra:
  val host: String = sys.env.getOrElse("CASSANDRA_HOST", "localhost")
  val port: Int = sys.env.getOrElse("CASSANDRA_PORT", "9042").toInt
  val keyspace = "sales"
  val table = "revenue_by_category"

  val schema: Seq[String] = Seq(
    s"CREATE KEYSPACE IF NOT EXISTS $keyspace WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}",
    s"CREATE TABLE IF NOT EXISTS $keyspace.$table (category text PRIMARY KEY, total_orders bigint, total_quantity bigint, total_revenue double)"
  )

  def session(): CqlSession =
    CqlSession.builder()
      .addContactPoint(InetSocketAddress(host, port))
      .withLocalDatacenter("datacenter1")
      .build()
