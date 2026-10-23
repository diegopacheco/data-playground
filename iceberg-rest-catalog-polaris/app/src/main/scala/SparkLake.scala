import org.apache.spark.sql.{DataFrame, SparkSession}

object SparkLake:

  import Model.{env, table}

  def session(app: String): SparkSession =
    val spark = SparkSession.builder()
      .appName(app)
      .master("local[2]")
      .config("spark.ui.enabled", "false")
      .config("spark.sql.shuffle.partitions", "4")
      .config("spark.sql.session.timeZone", "UTC")
      .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
      .config("spark.sql.catalog.polaris", "org.apache.iceberg.spark.SparkCatalog")
      .config("spark.sql.catalog.polaris.type", "rest")
      .config("spark.sql.catalog.polaris.uri", env("POLARIS_URL", "http://localhost:20902") + "/api/catalog")
      .config("spark.sql.catalog.polaris.warehouse", "i9_catalog")
      .config("spark.sql.catalog.polaris.credential", env("POLARIS_CREDENTIAL", ""))
      .config("spark.sql.catalog.polaris.scope", "PRINCIPAL_ROLE:ALL")
      .config("spark.sql.catalog.polaris.cache-enabled", "false")
      .config("spark.sql.catalog.polaris.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
      .config("spark.sql.catalog.polaris.s3.endpoint", env("S3_ENDPOINT", "http://localhost:20900"))
      .config("spark.sql.catalog.polaris.s3.path-style-access", "true")
      .config("spark.sql.catalog.polaris.s3.access-key-id", "i9admin")
      .config("spark.sql.catalog.polaris.s3.secret-access-key", "i9password")
      .config("spark.sql.catalog.polaris.client.region", "us-east-1")
      .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    spark

  def writeOrders(spark: SparkSession, csv: String): Long =
    spark.sql("CREATE NAMESPACE IF NOT EXISTS polaris.sales")
    spark.sql(s"DROP TABLE IF EXISTS $table PURGE")
    spark.sql(
      s"""CREATE TABLE $table (
         |order_id INT, customer STRING, product STRING, category STRING,
         |quantity INT, price DECIMAL(10,2), ts TIMESTAMP)
         |USING iceberg""".stripMargin
    )
    spark.read
      .option("header", "true")
      .schema("order_id INT, customer STRING, product STRING, category STRING, quantity INT, price DECIMAL(10,2), ts TIMESTAMP")
      .csv(csv)
      .writeTo(table)
      .append()
    spark.table(table).count()

  def aggregates(spark: SparkSession): List[Aggregate] =
    spark.sql(Model.aggregateSql).collect().toList.map { r =>
      Aggregate(r.getString(0), r.getLong(1), r.getLong(2), BigDecimal(r.getDecimal(3)))
    }

  def ordersFrom(spark: SparkSession, firstId: Int): DataFrame =
    spark.sql(
      s"""SELECT order_id, customer, product, category, quantity, price,
         |date_format(ts, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS ts
         |FROM $table WHERE order_id >= $firstId ORDER BY order_id""".stripMargin
    )

  def snapshots(spark: SparkSession): DataFrame =
    spark.sql(
      s"""SELECT CAST(snapshot_id AS STRING) AS snapshot_id, operation,
         |date_format(committed_at, 'yyyy-MM-dd HH:mm:ss.SSS') AS committed_at,
         |CASE WHEN summary['trino_query_id'] IS NOT NULL THEN 'trino' ELSE coalesce(summary['engine-name'], 'spark') END AS engine,
         |CAST(summary['added-records'] AS BIGINT) AS added_records,
         |CAST(summary['total-records'] AS BIGINT) AS total_records
         |FROM $table.snapshots ORDER BY committed_at""".stripMargin
    )
