import org.apache.spark.sql.SparkSession

object Lake:

  val bronze = "lake.bronze.orders_raw"
  val silver = "lake.silver.orders"
  val quarantine = "lake.silver.orders_quarantine"
  val goldRevenueByCategory = "lake.gold.revenue_by_category"
  val goldDailyRevenue = "lake.gold.daily_revenue"
  val goldTopCustomers = "lake.gold.top_customers"

  val gold = Seq(goldRevenueByCategory, goldDailyRevenue, goldTopCustomers)
  val layers = Seq("bronze" -> bronze, "silver" -> silver, "silver" -> quarantine) ++ gold.map("gold" -> _)

  private def env(name: String, default: String): String = sys.env.getOrElse(name, default)

  def session(app: String): SparkSession =
    val spark = SparkSession.builder()
      .appName(app)
      .master("local[2]")
      .config("spark.ui.enabled", "false")
      .config("spark.sql.shuffle.partitions", "4")
      .config("spark.sql.session.timeZone", "UTC")
      .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
      .config("spark.sql.catalog.lake", "org.apache.iceberg.spark.SparkCatalog")
      .config("spark.sql.catalog.lake.type", "rest")
      .config("spark.sql.catalog.lake.uri", env("CATALOG_URI", "http://localhost:25002"))
      .config("spark.sql.catalog.lake.warehouse", "s3://warehouse/")
      .config("spark.sql.catalog.lake.cache-enabled", "false")
      .config("spark.sql.catalog.lake.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
      .config("spark.sql.catalog.lake.s3.endpoint", env("S3_ENDPOINT", "http://localhost:25000"))
      .config("spark.sql.catalog.lake.s3.path-style-access", "true")
      .config("spark.sql.catalog.lake.s3.access-key-id", env("S3_ACCESS_KEY", "admin"))
      .config("spark.sql.catalog.lake.s3.secret-access-key", env("S3_SECRET_KEY", "password"))
      .config("spark.sql.catalog.lake.client.region", "us-east-1")
      .getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    spark

  def createNamespaces(spark: SparkSession): Unit =
    Seq("bronze", "silver", "gold").foreach(ns => spark.sql(s"CREATE NAMESPACE IF NOT EXISTS lake.$ns"))

  def exists(spark: SparkSession, table: String): Boolean = spark.catalog.tableExists(table)
