import org.apache.spark.sql.SparkSession

object Gold:

  val topCustomersLimit = 10

  private val revenueByCategorySql =
    s"""SELECT category, COUNT(*) AS orders, CAST(SUM(quantity) AS BIGINT) AS quantity,
       |CAST(SUM(quantity * price) AS DECIMAL(14,2)) AS revenue
       |FROM ${Lake.silver} GROUP BY category""".stripMargin

  private val dailyRevenueSql =
    s"""SELECT to_date(ts) AS order_date, COUNT(*) AS orders, CAST(SUM(quantity) AS BIGINT) AS quantity,
       |CAST(SUM(quantity * price) AS DECIMAL(14,2)) AS revenue
       |FROM ${Lake.silver} GROUP BY to_date(ts)""".stripMargin

  private val topCustomersSql =
    s"""SELECT CAST(rank AS INT) AS rank, customer, orders, revenue FROM (
       |  SELECT customer, COUNT(*) AS orders, CAST(SUM(quantity * price) AS DECIMAL(14,2)) AS revenue,
       |  row_number() OVER (ORDER BY SUM(quantity * price) DESC, customer ASC) AS rank
       |  FROM ${Lake.silver} GROUP BY customer
       |) WHERE rank <= $topCustomersLimit""".stripMargin

  private def replace(spark: SparkSession, table: String, sql: String): Unit =
    spark.sql(s"CREATE OR REPLACE TABLE $table USING iceberg AS $sql")

  def build(spark: SparkSession): Unit =
    replace(spark, Lake.goldRevenueByCategory, revenueByCategorySql)
    replace(spark, Lake.goldDailyRevenue, dailyRevenueSql)
    replace(spark, Lake.goldTopCustomers, topCustomersSql)

  def orderBy(table: String): String = table match
    case Lake.goldDailyRevenue => "order_date"
    case Lake.goldTopCustomers => "rank"
    case _ => "category"
