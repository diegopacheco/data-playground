import io.delta.tables.DeltaTable
import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.functions.*
import scala.util.Try

object DeltaJob:

  val schema = "order_id INT, customer STRING, product STRING, category STRING, quantity INT, price DECIMAL(10,2), ts TIMESTAMP"

  def readCsv(spark: SparkSession, file: String): DataFrame =
    spark.read.option("header", "true").schema(schema).csv(file)

  def atVersion(spark: SparkSession, location: String, version: Long): DataFrame =
    spark.read.format("delta").option("versionAsOf", version).load(location)

  def revenueByCategory(orders: DataFrame): DataFrame =
    orders
      .groupBy("category")
      .agg(count(lit(1)).as("orders"), sum(col("quantity") * col("price")).as("revenue"))

  def merge(spark: SparkSession, location: String, updates: DataFrame): Unit =
    DeltaTable.forPath(spark, location).as("t")
      .merge(updates.as("s"), "t.order_id = s.order_id")
      .whenMatched("t.price <> s.price").updateExpr(Map("price" -> "s.price"))
      .whenNotMatched().insertAll()
      .execute()

  def changeFeed(spark: SparkSession, location: String, from: Long, to: Long): DataFrame =
    spark.read.format("delta")
      .option("readChangeFeed", "true")
      .option("startingVersion", from)
      .option("endingVersion", to)
      .load(location)

  def versions(spark: SparkSession, location: String, upTo: Long): DataFrame =
    (0L to upTo)
      .map { v =>
        atVersion(spark, location, v)
          .agg(lit(v).as("version"), count(lit(1)).as("rows"), sum(col("quantity") * col("price")).as("revenue"))
      }
      .reduce(_ union _)

  def comparison(before: DataFrame, after: DataFrame): DataFrame =
    before.select(col("category"), col("orders").as("orders_before"), col("revenue").as("revenue_before"))
      .join(after.select(col("category"), col("orders").as("orders_after"), col("revenue").as("revenue_after")), Seq("category"), "full_outer")
      .withColumn("revenue_change", col("revenue_after") - col("revenue_before"))
      .orderBy("category")

  def history(spark: SparkSession, location: String): DataFrame =
    DeltaTable.forPath(spark, location).history()
      .select("version", "timestamp", "operation", "operationParameters", "operationMetrics")
      .orderBy("version")

  def rootCause(e: Throwable): Throwable =
    if e.getCause == null || e.getCause == e then e else rootCause(e.getCause)

  def vacuum(spark: SparkSession, location: String): String =
    val before = Lake.dataFiles(spark, location)
    val dryRun = spark.sql(s"VACUUM delta.`$location` RETAIN 0 HOURS DRY RUN").collect().map(r => Lake.relative(spark, location, r.getString(0))).toSeq.sorted
    spark.sql(s"VACUUM delta.`$location` RETAIN 0 HOURS").collect()
    val after = Lake.dataFiles(spark, location)
    val latest = spark.read.format("delta").load(location).count()
    val oldRead = Try(atVersion(spark, location, 0).collect().length)
    val oldStatus = oldRead.fold(e => s"failed: ${rootCause(e).getClass.getSimpleName}", n => s"ok: $n rows")
    println(s"vacuum removed ${before.size - after.size} files, version 0 read after vacuum -> $oldStatus")
    s"""{"retention_hours":0,"retention_check_enabled":false,"files_before":${Report.strings(before)},"dry_run":${Report.strings(dryRun)},"files_after":${Report.strings(after)},"latest_rows_after_vacuum":$latest,"version0_after_vacuum":${Report.quote(oldStatus)}}"""

  def main(args: Array[String]): Unit =
    val location = Lake.env("TABLE_PATH", "s3a://lake/orders")
    val out = Lake.env("OUTPUT_DIR", "output")
    val spark = Lake.session()
    spark.sparkContext.setLogLevel("WARN")

    Lake.reset(spark, location)
    readCsv(spark, "data/orders.csv").write.format("delta").save(location)
    println("version 0 written")

    merge(spark, location, readCsv(spark, "data/updates.csv"))
    println("version 1 merged")

    val before = revenueByCategory(atVersion(spark, location, 0))
    val after = revenueByCategory(atVersion(spark, location, 1))
    val cdf = changeFeed(spark, location, 1, 1)
    comparison(before, after).show(false)
    cdf.groupBy("_change_type").count().orderBy("_change_type").show(false)

    Report.write(out, "revenue", Report.rows(comparison(before, after)))
    Report.write(out, "versions", Report.rows(versions(spark, location, 1)))
    Report.write(out, "changes", Report.rows(
      cdf.select("order_id", "customer", "category", "quantity", "price", "_change_type", "_commit_version", "_commit_timestamp")
        .orderBy(col("order_id"), col("_change_type").desc)
    ))
    Report.write(out, "change_summary", Report.rows(cdf.groupBy("_change_type").count().orderBy("_change_type")))
    Report.write(out, "vacuum", vacuum(spark, location))
    Report.write(out, "history", Report.rows(history(spark, location)))
    spark.stop()
