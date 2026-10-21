import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.functions.*
import org.apache.spark.sql.types.*

final case class CategoryTotal(category: String, orders: Long, quantity: Long, revenue: String)

object Orders:

  val IdStride = 10000L

  private val schema = StructType(Seq(
    StructField("order_id", LongType),
    StructField("customer", StringType),
    StructField("product", StringType),
    StructField("category", StringType),
    StructField("quantity", IntegerType),
    StructField("price", DecimalType(10, 2)),
    StructField("ts", StringType)
  ))

  def load(spark: SparkSession, path: String): DataFrame =
    spark.read.option("header", "true").schema(schema).csv(path)

  def expand(base: DataFrame, copies: Int): DataFrame =
    base
      .crossJoin(base.sparkSession.range(copies).withColumnRenamed("id", "copy"))
      .select(
        (col("copy") * IdStride + col("order_id")).as("order_id"),
        col("customer"),
        col("product"),
        col("category"),
        (col("quantity") + (col("copy") % 3).cast("int")).as("quantity"),
        col("price"),
        col("ts"),
        lit(0L).as("version")
      )

  def upsertBatch(orders: DataFrame, batch: Int): DataFrame =
    orders
      .filter(col("order_id") % 10 === batch - 1)
      .withColumn("quantity", col("quantity") + batch)
      .withColumn("ts", lit(f"2026-03-$batch%02dT00:00:00Z"))
      .withColumn("version", lit(batch.toLong))

  def aggregate(df: DataFrame): Seq[CategoryTotal] =
    df.groupBy("category")
      .agg(
        count(lit(1)).as("orders"),
        sum("quantity").as("quantity"),
        sum(col("quantity") * col("price")).as("revenue")
      )
      .collect()
      .map(r => CategoryTotal(r.getString(0), r.getLong(1), r.getLong(2), r.getDecimal(3).setScale(2).toPlainString))
      .sortBy(_.category)
      .toSeq
