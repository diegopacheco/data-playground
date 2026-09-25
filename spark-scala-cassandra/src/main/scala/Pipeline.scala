import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.functions.{col, count, round, sum}
import org.apache.spark.sql.types.{LongType, StructType}

object Pipeline:
  val ordersSchema: StructType = StructType.fromDDL(
    "order_id INT, customer STRING, product STRING, category STRING, quantity INT, price DOUBLE, ts STRING"
  )

  def revenueByCategory(orders: DataFrame): DataFrame =
    orders
      .groupBy(col("category"))
      .agg(
        count("*").as("total_orders"),
        sum(col("quantity")).cast(LongType).as("total_quantity"),
        round(sum(col("quantity") * col("price")), 2).as("total_revenue")
      )

  def createSchema(): Unit =
    val session = Cassandra.session()
    try Cassandra.schema.foreach(session.execute)
    finally session.close()

  def main(args: Array[String]): Unit =
    val input = args.headOption.getOrElse("data/orders.csv")
    createSchema()
    val spark = SparkSession.builder()
      .appName("revenue-by-category")
      .master("local[*]")
      .config("spark.cassandra.connection.host", Cassandra.host)
      .config("spark.cassandra.connection.port", Cassandra.port.toString)
      .getOrCreate()
    try
      val orders = spark.read.option("header", "true").schema(ordersSchema).csv(input)
      val result = revenueByCategory(orders)
      result.show(truncate = false)
      result.write
        .format("org.apache.spark.sql.cassandra")
        .option("keyspace", Cassandra.keyspace)
        .option("table", Cassandra.table)
        .mode("append")
        .save()
      println(s"wrote ${result.count()} rows to ${Cassandra.keyspace}.${Cassandra.table}")
    finally spark.stop()
