import org.apache.spark.sql.{DataFrame, SaveMode, SparkSession}

enum TableKind(val hudiType: String, val label: String):
  case Cow extends TableKind("COPY_ON_WRITE", "cow")
  case Mor extends TableKind("MERGE_ON_READ", "mor")

final case class HudiTable(kind: TableKind, path: String):

  private def options(operation: String): Map[String, String] = Map(
    "hoodie.table.name" -> s"orders_${kind.label}",
    "hoodie.datasource.write.table.type" -> kind.hudiType,
    "hoodie.datasource.write.operation" -> operation,
    "hoodie.datasource.write.recordkey.field" -> "order_id",
    "hoodie.datasource.write.precombine.field" -> "version",
    "hoodie.datasource.write.partitionpath.field" -> "category",
    "hoodie.datasource.write.hive_style_partitioning" -> "true",
    "hoodie.insert.shuffle.parallelism" -> "4",
    "hoodie.upsert.shuffle.parallelism" -> "4",
    "hoodie.compact.inline" -> "false",
    "hoodie.datasource.compaction.async.enable" -> "false"
  )

  def write(df: DataFrame, operation: String, mode: SaveMode): Unit =
    df.write.format("hudi").options(options(operation)).mode(mode).save(path)

  def snapshot(spark: SparkSession): DataFrame =
    spark.read.format("hudi").load(path)

  def readOptimized(spark: SparkSession): DataFrame =
    spark.read.format("hudi").option("hoodie.datasource.query.type", "read_optimized").load(path)

  def compact(spark: SparkSession): Unit =
    spark
      .sql(s"CALL run_compaction(op => 'scheduleAndExecute', path => '$path', options => 'hoodie.compact.inline.max.delta.commits=1')")
      .collect()
      .foreach(r => println(s"compaction $r"))
