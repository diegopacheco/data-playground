import org.apache.spark.sql.SparkSession

object Silver:

  def create(spark: SparkSession): Unit =
    spark.sql(
      s"""CREATE TABLE IF NOT EXISTS ${Lake.silver} (
         |order_id INT, customer STRING, product STRING, category STRING,
         |quantity INT, price DECIMAL(10,2), ts TIMESTAMP,
         |_source_file STRING, _line INT, _ingested_at TIMESTAMP)
         |USING iceberg PARTITIONED BY (category)""".stripMargin
    )
    spark.sql(
      s"""CREATE TABLE IF NOT EXISTS ${Lake.quarantine} (
         |order_id STRING, customer STRING, product STRING, category STRING,
         |quantity STRING, price STRING, ts STRING, reason STRING,
         |_source_file STRING, _line INT, _ingested_at TIMESTAMP)
         |USING iceberg""".stripMargin
    )

  private val checkedSql =
    s"""SELECT *,
       |CASE
       |  WHEN o NOT RLIKE '^[0-9]+$$' THEN 'invalid order_id'
       |  WHEN cu = '' THEN 'missing customer'
       |  WHEN ca = '' THEN 'missing category'
       |  WHEN q NOT RLIKE '^-?[0-9]+$$' THEN 'malformed quantity'
       |  WHEN try_cast(q AS INT) IS NULL OR try_cast(q AS INT) <= 0 THEN 'non-positive quantity'
       |  WHEN p NOT RLIKE '^[0-9]+([.][0-9]{1,2})?$$' THEN 'malformed price'
       |  WHEN try_cast(p AS DECIMAL(10,2)) <= 0 THEN 'non-positive price'
       |  WHEN t NOT RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$$'
       |    OR try_cast(t AS TIMESTAMP) IS NULL THEN 'malformed ts'
       |END AS reason
       |FROM (
       |  SELECT *,
       |  coalesce(trim(order_id), '') AS o, coalesce(trim(customer), '') AS cu,
       |  coalesce(trim(category), '') AS ca, coalesce(trim(quantity), '') AS q,
       |  coalesce(trim(price), '') AS p, coalesce(trim(ts), '') AS t
       |  FROM ${Lake.bronze}
       |)""".stripMargin

  private val latestSql =
    s"""SELECT order_id, customer, product, category, quantity, price, ts, _source_file, _line, _ingested_at
      |FROM (
      |  SELECT CAST(o AS INT) AS order_id, cu AS customer, trim(product) AS product, lower(ca) AS category,
      |  CAST(q AS INT) AS quantity, CAST(p AS DECIMAL(10,2)) AS price, CAST(t AS TIMESTAMP) AS ts,
      |  _source_file, _line, _ingested_at,
      |  row_number() OVER (PARTITION BY CAST(o AS INT) ORDER BY _ingested_at DESC, _source_file DESC, _line DESC) AS rn
      |  FROM ($checkedSql) WHERE reason IS NULL
      |) WHERE rn = 1""".stripMargin

  private val mergeSilverSql =
    s"""MERGE INTO ${Lake.silver} t USING ($latestSql) s
       |ON t.order_id = s.order_id
       |WHEN MATCHED AND struct(s._ingested_at, s._source_file, s._line) > struct(t._ingested_at, t._source_file, t._line)
       |  THEN UPDATE SET *
       |WHEN NOT MATCHED THEN INSERT *""".stripMargin

  private val mergeQuarantineSql =
    s"""MERGE INTO ${Lake.quarantine} t USING (
       |  SELECT order_id, customer, product, category, quantity, price, ts, reason, _source_file, _line, _ingested_at
       |  FROM ($checkedSql) WHERE reason IS NOT NULL
       |) s
       |ON t._source_file = s._source_file AND t._line = s._line
       |WHEN NOT MATCHED THEN INSERT *""".stripMargin

  def build(spark: SparkSession): Unit =
    spark.sql(mergeSilverSql)
    spark.sql(mergeQuarantineSql)
