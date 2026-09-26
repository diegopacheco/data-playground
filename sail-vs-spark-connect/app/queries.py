import inspect
from pyspark.sql import Window
from pyspark.sql import functions as F

Q1 = """SELECT status, COUNT(*) AS orders, SUM(quantity) AS units, SUM(quantity * price_cents) AS revenue_cents
FROM orders
GROUP BY status
ORDER BY status"""

Q3 = """SELECT p.category, p.supplier, COUNT(*) AS orders, COUNT(DISTINCT o.customer_id) AS customers,
       SUM(o.quantity * o.price_cents) AS revenue_cents
FROM orders o JOIN products p ON o.product_id = p.product_id
WHERE o.status = 'completed'
GROUP BY p.category, p.supplier
ORDER BY p.category, p.supplier"""

Q4 = """WITH product_revenue AS (
  SELECT region, product_id, SUM(quantity * price_cents) AS revenue_cents
  FROM orders
  WHERE status = 'completed'
  GROUP BY region, product_id
), ranked AS (
  SELECT region, product_id, revenue_cents,
         ROW_NUMBER() OVER (PARTITION BY region ORDER BY revenue_cents DESC, product_id) AS rank
  FROM product_revenue
)
SELECT region, rank, product_id, revenue_cents
FROM ranked
WHERE rank <= 3
ORDER BY region, rank"""

Q6 = """WITH per_customer AS (
  SELECT customer_id, COUNT(*) AS orders, SUM(quantity * price_cents) AS revenue_cents
  FROM orders
  WHERE order_date >= DATE '2026-01-01' AND channel IN ('web', 'mobile') AND status <> 'cancelled'
  GROUP BY customer_id
  HAVING COUNT(*) >= 20
)
SELECT orders, COUNT(*) AS customers, SUM(revenue_cents) AS revenue_cents
FROM per_customer
GROUP BY orders
ORDER BY orders"""

Q7 = """SELECT region, channel, COUNT(*) AS orders, SUM(quantity * price_cents) AS revenue_cents
FROM orders
GROUP BY ROLLUP (region, channel)
ORDER BY region NULLS LAST, channel NULLS LAST"""

Q8 = """SELECT *
FROM (SELECT region, status, quantity FROM orders)
PIVOT (SUM(quantity) FOR status IN ('completed', 'returned', 'cancelled'))
ORDER BY region"""


def top_customers(spark):
    orders = spark.table("orders")
    return (orders.filter(F.col("status") == "completed")
            .groupBy("customer_id")
            .agg(F.sum(F.col("quantity") * F.col("price_cents")).alias("revenue_cents"),
                 F.count("*").alias("orders"))
            .orderBy(F.desc("revenue_cents"), "customer_id")
            .limit(10))


def monthly_running_total(spark):
    orders = spark.table("orders")
    monthly = (orders.filter(F.col("status") == "completed")
               .groupBy("channel", F.year("order_date").alias("year"), F.month("order_date").alias("month"))
               .agg(F.sum(F.col("quantity") * F.col("price_cents")).alias("revenue_cents")))
    by_month = Window.partitionBy("channel").orderBy("year", "month")
    return (monthly
            .withColumn("running_cents", F.sum("revenue_cents").over(by_month.rowsBetween(Window.unboundedPreceding, 0)))
            .withColumn("previous_cents", F.lag("revenue_cents").over(by_month))
            .orderBy("channel", "year", "month"))


def basket_stats(spark):
    orders = spark.table("orders")
    return (orders.withColumn("line_cents", F.col("quantity") * F.col("price_cents"))
            .groupBy("channel")
            .agg(F.round(F.avg("line_cents") / 100, 2).alias("avg_line"),
                 F.median("price_cents").alias("median_price_cents"),
                 F.min("line_cents").alias("min_line_cents"),
                 F.max("line_cents").alias("max_line_cents"))
            .orderBy("channel"))


def sql(text):
    return lambda spark: spark.sql(text)


def query(qid, title, kind, run, text):
    return {"id": qid, "title": title, "kind": kind, "run": run, "text": text}


def dataframe(qid, title, fn):
    return query(qid, title, "DataFrame API", fn, inspect.getsource(fn).strip())


def spark_sql(qid, title, text):
    return query(qid, title, "Spark SQL", sql(text), text)


QUERIES = [
    spark_sql("q1", "Aggregate by status", Q1),
    dataframe("q2", "Top 10 customers by completed revenue", top_customers),
    spark_sql("q3", "Join with products, revenue per category and supplier", Q3),
    spark_sql("q4", "Top 3 products per region (ROW_NUMBER window)", Q4),
    dataframe("q5", "Monthly revenue per channel with running total and lag", monthly_running_total),
    spark_sql("q6", "Loyal customers in 2026 (filter + HAVING)", Q6),
    spark_sql("q7", "Revenue ROLLUP by region and channel", Q7),
    spark_sql("q8", "Units PIVOT by region and status", Q8),
    dataframe("q9", "Basket stats per channel (avg, exact median)", basket_stats),
]
