object Pipeline:

  private def step(title: String): Unit = println(s"\n== $title")

  def main(args: Array[String]): Unit =
    val spark = SparkLake.session("polaris-pipeline")
    val inserts = Model.readCsv(Model.env("TRINO_INSERTS_CSV", "data/trino_inserts.csv"))

    step(s"spark writes ${Model.table} through polaris")
    val written = SparkLake.writeOrders(spark, Model.env("ORDERS_CSV", "data/orders.csv"))
    println(s"SPARK_WRITTEN $written")

    step("trino reads the same table through polaris and aggregates per category")
    Model.show("TRINO_BEFORE", TrinoLake.aggregates())

    step(s"trino inserts ${inserts.size} rows")
    println(s"TRINO_INSERTED ${TrinoLake.insert(inserts)}")

    step("spark reads back the rows trino wrote")
    val readBack = SparkLake.ordersFrom(spark, Model.trinoFirstId)
    readBack.show(false)
    println(s"SPARK_READBACK ${readBack.count()}")
    Model.show("SPARK_AFTER", SparkLake.aggregates(spark))

    step("snapshots")
    SparkLake.snapshots(spark).show(false)
    spark.stop()
