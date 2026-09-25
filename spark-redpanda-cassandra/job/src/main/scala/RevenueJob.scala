import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.functions.*

object RevenueJob:

  private def env(name: String, default: String): String = sys.env.getOrElse(name, default)

  def readOrders(spark: SparkSession, bootstrap: String, topic: String): DataFrame =
    val fields = split(col("value").cast("string"), ",")
    spark.read
      .format("kafka")
      .option("kafka.bootstrap.servers", bootstrap)
      .option("subscribe", topic)
      .option("startingOffsets", "earliest")
      .option("endingOffsets", "latest")
      .load()
      .select(
        fields.getItem(3).as("category"),
        fields.getItem(4).cast("long").as("quantity"),
        fields.getItem(5).cast("double").as("price")
      )

  def revenueByCategory(orders: DataFrame): DataFrame =
    orders
      .groupBy("category")
      .agg(
        count(lit(1)).as("total_orders"),
        sum("quantity").as("total_quantity"),
        round(sum(col("quantity") * col("price")), 2).as("total_revenue")
      )

  def main(args: Array[String]): Unit =
    val spark = SparkSession.builder()
      .appName("revenue-job")
      .master("local[*]")
      .config("spark.cassandra.connection.host", env("CASSANDRA_HOST", "localhost"))
      .config("spark.cassandra.connection.port", env("CASSANDRA_PORT", "16042"))
      .config("spark.ui.enabled", "false")
      .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    val result = revenueByCategory(readOrders(spark, env("KAFKA_BOOTSTRAP", "localhost:16092"), env("KAFKA_TOPIC", "orders")))
    result.orderBy("category").show(false)
    result.write
      .format("org.apache.spark.sql.cassandra")
      .option("keyspace", "sales")
      .option("table", "revenue_by_category")
      .mode("append")
      .save()
    spark.stop()
