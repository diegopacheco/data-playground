case class Aggregate(category: String, orders: Long, quantity: Long, revenue: BigDecimal)

case class Order(orderId: Int, customer: String, product: String, category: String, quantity: Int, price: BigDecimal, ts: String)

object Model:

  val table = "polaris.sales.orders"
  val trinoFirstId = 5001

  val aggregateSql: String =
    s"""SELECT category, COUNT(*) AS orders, SUM(quantity) AS quantity, SUM(quantity * price) AS revenue
       |FROM $table GROUP BY category ORDER BY category""".stripMargin

  def env(name: String, default: String): String = sys.env.getOrElse(name, default)

  def readCsv(path: String): List[Order] =
    val source = scala.io.Source.fromFile(path)
    try
      source.getLines().drop(1).filter(_.nonEmpty).map { line =>
        val c = line.split(",", -1)
        Order(c(0).toInt, c(1), c(2), c(3), c(4).toInt, BigDecimal(c(5)), c(6))
      }.toList
    finally source.close()

  def show(label: String, rows: Seq[Aggregate]): Unit =
    rows.foreach(a => println(s"$label ${a.category} ${a.orders} ${a.quantity} ${a.revenue.setScale(2)}"))
