object Json:

  def str(s: String): String = "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

  def obj(fields: (String, String)*): String =
    fields.map((k, v) => s"${str(k)}:$v").mkString("{", ",", "}")

  def arr(items: Seq[String]): String = items.mkString("[", ",", "]")

  def opt(v: Option[Long]): String = v.fold("null")(_.toString)

  def totals(rows: Seq[CategoryTotal]): String =
    arr(rows.map(t => obj(
      "category" -> str(t.category),
      "orders" -> t.orders.toString,
      "quantity" -> t.quantity.toString,
      "revenue" -> str(t.revenue)
    )))

  def storage(s: StorageStats): String = obj(
    "baseFiles" -> s.baseFiles.toString,
    "logFiles" -> s.logFiles.toString,
    "otherFiles" -> s.otherFiles.toString,
    "baseBytes" -> s.baseBytes.toString,
    "logBytes" -> s.logBytes.toString,
    "dataBytes" -> s.dataBytes.toString,
    "totalBytes" -> s.totalBytes.toString
  )
