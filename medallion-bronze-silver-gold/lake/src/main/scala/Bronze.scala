import java.io.File
import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.expressions.Window
import org.apache.spark.sql.functions.{current_timestamp, lit, monotonically_increasing_id, row_number}
import org.apache.spark.sql.types.{StringType, StructField, StructType}

object Bronze:

  private val columns = Seq("order_id", "customer", "product", "category", "quantity", "price", "ts")
  private val schema = StructType(columns.map(StructField(_, StringType)))

  def create(spark: SparkSession): Unit =
    spark.sql(
      s"""CREATE TABLE IF NOT EXISTS ${Lake.bronze} (
         |order_id STRING, customer STRING, product STRING, category STRING,
         |quantity STRING, price STRING, ts STRING,
         |_source_file STRING, _line INT, _ingested_at TIMESTAMP)
         |USING iceberg""".stripMargin
    )

  def ingestedFiles(spark: SparkSession): Set[String] =
    spark.sql(s"SELECT DISTINCT _source_file FROM ${Lake.bronze}").collect().map(_.getString(0)).toSet

  def landingFiles(dir: String): Seq[File] =
    Option(File(dir).listFiles()).toSeq.flatten.filter(_.getName.endsWith(".csv")).sortBy(_.getName)

  def read(spark: SparkSession, file: File): DataFrame =
    spark.read
      .option("header", "true")
      .schema(schema)
      .csv(file.getPath)
      .coalesce(1)
      .withColumn("_source_file", lit(file.getName))
      .withColumn("_line", (row_number().over(Window.orderBy(monotonically_increasing_id())) + 1).cast("int"))
      .withColumn("_ingested_at", current_timestamp())

  def ingest(spark: SparkSession, dir: String): Seq[(String, Long)] =
    val done = ingestedFiles(spark)
    landingFiles(dir).filterNot(f => done.contains(f.getName)).map { file =>
      val df = read(spark, file).cache()
      df.writeTo(Lake.bronze).append()
      val rows = df.count()
      df.unpersist()
      file.getName -> rows
    }
