import java.sql.{Connection, DriverManager}

object TrinoLake:

  private def url: String = s"jdbc:trino://localhost:${Model.env("TRINO_PORT", "20904")}/polaris/sales"

  private def withConnection[A](f: Connection => A): A =
    val connection = DriverManager.getConnection(url, "i9", null)
    try f(connection)
    finally connection.close()

  def aggregates(): List[Aggregate] =
    withConnection { c =>
      val rs = c.createStatement().executeQuery(Model.aggregateSql)
      Iterator.continually(rs).takeWhile(_.next()).map { r =>
        Aggregate(r.getString(1), r.getLong(2), r.getLong(3), BigDecimal(r.getBigDecimal(4)))
      }.toList
    }

  private def literal(s: String): String = "'" + s.replace("'", "''") + "'"

  def insertSql(orders: List[Order]): String =
    val values = orders.map { o =>
      val ts = o.ts.replace("T", " ").stripSuffix("Z")
      s"(${o.orderId}, ${literal(o.customer)}, ${literal(o.product)}, ${literal(o.category)}, ${o.quantity}, " +
        s"DECIMAL '${o.price}', TIMESTAMP '$ts UTC')"
    }
    s"INSERT INTO ${Model.table} VALUES ${values.mkString(", ")}"

  def insert(orders: List[Order]): Long =
    withConnection(_.createStatement().executeLargeUpdate(insertSql(orders)))
