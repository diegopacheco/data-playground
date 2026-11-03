import org.apache.spark.sql.{DataFrame, SparkSession}

object Queries:

  def layers(spark: SparkSession): DataFrame =
    Lake.layers.filter((_, t) => Lake.exists(spark, t)).map { (layer, table) =>
      spark.sql(
        s"""SELECT '$layer' AS layer, '${table.stripPrefix("lake.")}' AS table_name,
           |(SELECT COUNT(*) FROM $table) AS row_count,
           |(SELECT COUNT(*) FROM $table.snapshots) AS snapshots,
           |(SELECT CAST(snapshot_id AS STRING) FROM $table.snapshots ORDER BY committed_at DESC LIMIT 1) AS current_snapshot""".stripMargin
      )
    }.reduce(_ unionAll _)

  def bronzeFiles(spark: SparkSession): DataFrame =
    spark.sql(
      s"""SELECT _source_file AS source_file, COUNT(*) AS row_count,
         |date_format(MIN(_ingested_at), 'yyyy-MM-dd HH:mm:ss') AS ingested_at
         |FROM ${Lake.bronze} GROUP BY _source_file ORDER BY _source_file""".stripMargin
    )

  def quarantineReasons(spark: SparkSession): DataFrame =
    spark.sql(s"SELECT reason, COUNT(*) AS row_count FROM ${Lake.quarantine} GROUP BY reason ORDER BY reason")

  def quarantineRows(spark: SparkSession): DataFrame =
    spark.sql(
      s"""SELECT reason, _source_file AS source_file, _line AS line, order_id, customer, product, category, quantity, price, ts
         |FROM ${Lake.quarantine} ORDER BY _source_file, _line""".stripMargin
    )

  def silverFromLaterFiles(spark: SparkSession): DataFrame =
    spark.sql(
      s"""SELECT order_id, customer, product, category, quantity, price,
         |date_format(ts, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS ts, _source_file AS source_file, _line AS line
         |FROM ${Lake.silver}
         |WHERE _source_file > (SELECT MIN(_source_file) FROM ${Lake.bronze})
         |ORDER BY order_id""".stripMargin
    )

  def gold(spark: SparkSession, table: String): DataFrame =
    spark.sql(s"SELECT * FROM $table ORDER BY ${Gold.orderBy(table)}")
