import org.apache.spark.sql.DataFrame

object Json:

  def quote(s: String): String = "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

  private def value(v: Any): String = v match
    case null => "null"
    case s: String => quote(s)
    case d: java.math.BigDecimal => d.toPlainString
    case n: Number => n.toString
    case b: Boolean => b.toString
    case o => quote(o.toString)

  def aggregates(rows: Seq[Aggregate]): String =
    rows.map { a =>
      s"""{"category":${quote(a.category)},"orders":${a.orders},"quantity":${a.quantity},"revenue":${a.revenue.setScale(2).toString}}"""
    }.mkString("[", ",", "]")

  def frame(df: DataFrame): String =
    val names = df.columns
    df.collect()
      .map(r => names.indices.map(i => s"${quote(names(i))}:${value(r.get(i))}").mkString("{", ",", "}"))
      .mkString("[", ",", "]")
