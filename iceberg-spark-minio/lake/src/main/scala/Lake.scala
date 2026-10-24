import org.apache.spark.sql.{DataFrame, SparkSession}

object Lake:

  val table = "lake.sales.orders"

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
      .config("spark.sql.catalog.lake.uri", env("CATALOG_URI", "http://localhost:20102"))
      .config("spark.sql.catalog.lake.warehouse", "s3://warehouse/")
      .config("spark.sql.catalog.lake.cache-enabled", "false")
      .config("spark.sql.catalog.lake.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
      .config("spark.sql.catalog.lake.s3.endpoint", env("S3_ENDPOINT", "http://localhost:20100"))
      .config("spark.sql.catalog.lake.s3.path-style-access", "true")
      .config("spark.sql.catalog.lake.s3.access-key-id", env("S3_ACCESS_KEY", "admin"))
      .config("spark.sql.catalog.lake.s3.secret-access-key", env("S3_SECRET_KEY", "password"))
      .config("spark.sql.catalog.lake.client.region", "us-east-1")
      .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    spark

  def snapshots(spark: SparkSession): DataFrame =
    spark.sql(
      s"""SELECT snapshot_id, parent_id, operation,
         |date_format(committed_at, 'yyyy-MM-dd HH:mm:ss.SSS') AS committed_at,
         |CAST(summary['added-records'] AS BIGINT) AS added_records,
         |CAST(summary['total-records'] AS BIGINT) AS total_records
         |FROM $table.snapshots ORDER BY committed_at""".stripMargin
    )

  def revenueAt(spark: SparkSession, snapshotId: Long): DataFrame =
    spark.sql(
      s"""SELECT category, COUNT(*) AS orders, SUM(quantity) AS quantity, SUM(quantity * price) AS revenue
         |FROM $table VERSION AS OF $snapshotId GROUP BY category ORDER BY category""".stripMargin
    )
