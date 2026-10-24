import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.functions.col

object LakeJob:

  private val table = Lake.table
  private val firstBatchLastId = 1100

  private def step(title: String): Unit = println(s"\n== $title")

  def readOrders(spark: SparkSession, path: String): DataFrame =
    spark.read
      .option("header", "true")
      .schema("order_id INT, customer STRING, product STRING, category STRING, quantity INT, price DECIMAL(10,2), ts TIMESTAMP")
      .csv(path)

  def createTable(spark: SparkSession): Unit =
    spark.sql("CREATE NAMESPACE IF NOT EXISTS lake.sales")
    spark.sql(s"DROP TABLE IF EXISTS $table PURGE")
    spark.sql(
      s"""CREATE TABLE $table (
         |order_id INT, customer STRING, product STRING, category STRING,
         |quantity INT, price DECIMAL(10,2), ts TIMESTAMP)
         |USING iceberg PARTITIONED BY (category)""".stripMargin
    )

  def evolveSchema(spark: SparkSession): Unit =
    spark.sql(s"ALTER TABLE $table ADD COLUMN channel STRING")
    spark.sql(s"ALTER TABLE $table RENAME COLUMN customer TO customer_name")

  def main(args: Array[String]): Unit =
    val spark = Lake.session("iceberg-lake-job")
    val orders = readOrders(spark, sys.env.getOrElse("ORDERS_CSV", "data/orders.csv"))

    step("create table + first append")
    createTable(spark)
    orders.filter(col("order_id") <= firstBatchLastId).writeTo(table).append()

    step("second append")
    orders.filter(col("order_id") > firstBatchLastId).writeTo(table).append()

    step("snapshots")
    val snaps = Lake.snapshots(spark).collect()
    Lake.snapshots(spark).show(false)
    spark.sql(s"SELECT * FROM $table.history").show(false)
    val first = snaps.head
    val latest = snaps.last
    val firstId = first.getAs[Long]("snapshot_id")
    val latestId = latest.getAs[Long]("snapshot_id")
    val firstTs = first.getAs[String]("committed_at")

    step(s"time travel VERSION AS OF $firstId")
    spark.sql(s"SELECT COUNT(*) AS total_rows FROM $table VERSION AS OF $firstId").show()
    step(s"time travel TIMESTAMP AS OF '$firstTs'")
    spark.sql(s"SELECT COUNT(*) AS total_rows FROM $table TIMESTAMP AS OF '$firstTs'").show()
    step("latest")
    spark.sql(s"SELECT COUNT(*) AS total_rows FROM $table").show()

    step("schema evolution: add column channel, rename customer to customer_name")
    evolveSchema(spark)
    spark.sql(s"DESCRIBE TABLE $table").show(false)
    spark.sql(s"SELECT order_id, customer_name, channel, category FROM $table ORDER BY order_id LIMIT 3").show(false)
    step(s"old snapshot $firstId still reads with its own schema")
    spark.sql(s"SELECT * FROM $table VERSION AS OF $firstId ORDER BY order_id LIMIT 3").show(false)

    step(s"revenue by category at first snapshot $firstId")
    Lake.revenueAt(spark, firstId).show(false)
    step(s"revenue by category at latest snapshot $latestId")
    Lake.revenueAt(spark, latestId).show(false)

    spark.stop()
