import org.apache.spark.sql.SparkSession

object LakeJob:

  private def step(title: String): Unit = println(s"\n== $title")

  private def reset(spark: SparkSession): Unit =
    Lake.layers.map(_._2).foreach(t => spark.sql(s"DROP TABLE IF EXISTS $t PURGE"))

  def main(args: Array[String]): Unit =
    val spark = Lake.session("medallion-lake-job")
    val landing = sys.env.getOrElse("LANDING_DIR", "data/landing")
    Lake.createNamespaces(spark)
    if args.contains("reset") then
      step("reset: dropping every medallion table")
      reset(spark)

    step("bronze: ingest new landing files as raw strings")
    Bronze.create(spark)
    val ingested = Bronze.ingest(spark, landing)
    if ingested.isEmpty then println("no new files, bronze unchanged")
    ingested.foreach((f, n) => println(s"ingested $f rows=$n"))
    Queries.bronzeFiles(spark).show(false)

    step("silver: validate, quarantine, dedup latest by order_id, MERGE INTO")
    Silver.create(spark)
    Silver.build(spark)
    Queries.quarantineReasons(spark).show(false)
    Queries.silverFromLaterFiles(spark).show(false)

    step("gold: rebuild aggregates from silver")
    Gold.build(spark)
    Lake.gold.foreach { t =>
      println(t)
      Queries.gold(spark, t).show(50, false)
    }

    step("layers")
    Queries.layers(spark).show(false)
    spark.stop()
