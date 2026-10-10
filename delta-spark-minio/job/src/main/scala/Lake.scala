import org.apache.hadoop.fs.Path
import org.apache.spark.sql.SparkSession

object Lake:

  def env(name: String, default: String): String = sys.env.getOrElse(name, default)

  def session(): SparkSession =
    SparkSession.builder()
      .appName("delta-job")
      .master("local[2]")
      .config("spark.ui.enabled", "false")
      .config("spark.sql.shuffle.partitions", "2")
      .config("spark.sql.session.timeZone", "UTC")
      .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
      .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
      .config("spark.databricks.delta.properties.defaults.enableChangeDataFeed", "true")
      .config("spark.databricks.delta.retentionDurationCheck.enabled", "false")
      .config("spark.databricks.delta.vacuum.logging.enabled", "true")
      .config("spark.hadoop.fs.s3a.endpoint", env("S3_ENDPOINT", "http://localhost:20200"))
      .config("spark.hadoop.fs.s3a.endpoint.region", "us-east-1")
      .config("spark.hadoop.fs.s3a.access.key", env("S3_ACCESS_KEY", "admin"))
      .config("spark.hadoop.fs.s3a.secret.key", env("S3_SECRET_KEY", "password"))
      .config("spark.hadoop.fs.s3a.path.style.access", "true")
      .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
      .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
      .getOrCreate()

  def reset(spark: SparkSession, location: String): Unit =
    val path = Path(location)
    val fs = path.getFileSystem(spark.sparkContext.hadoopConfiguration)
    if fs.exists(path) then fs.delete(path, true)

  def relative(spark: SparkSession, location: String, file: String): String =
    val path = Path(location)
    val fs = path.getFileSystem(spark.sparkContext.hadoopConfiguration)
    fs.makeQualified(path).toUri.relativize(fs.makeQualified(Path(file)).toUri).toString

  def dataFiles(spark: SparkSession, location: String): Seq[String] =
    val path = Path(location)
    val fs = path.getFileSystem(spark.sparkContext.hadoopConfiguration)
    val it = fs.listFiles(path, true)
    val files = Seq.newBuilder[String]
    while it.hasNext do
      val name = relative(spark, location, it.next().getPath.toString)
      if name.endsWith(".parquet") && !name.startsWith("_delta_log") then files += name
    files.result().sorted
