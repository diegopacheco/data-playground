import org.apache.spark.sql.{DataFrame, SaveMode, SparkSession}
import java.nio.file.{Files, Path, Paths}

final case class Step(
    name: String,
    writeMs: Long,
    snapshotMs: Long,
    snapshotRows: Long,
    readOptimizedMs: Option[Long],
    readOptimizedRows: Option[Long],
    storage: StorageStats
):
  def json: String = Json.obj(
    "step" -> Json.str(name),
    "writeMs" -> writeMs.toString,
    "snapshotMs" -> snapshotMs.toString,
    "snapshotRows" -> snapshotRows.toString,
    "readOptimizedMs" -> Json.opt(readOptimizedMs),
    "readOptimizedRows" -> Json.opt(readOptimizedRows),
    "storage" -> Json.storage(storage)
  )

final case class Run(steps: Seq[Step], snapshots: Map[String, Seq[CategoryTotal]])

object HudiBench:

  private val Copies = 2500
  private val Batches = 3

  private def env(name: String, default: String): String = sys.env.getOrElse(name, default)

  private def timed[A](f: => A): (A, Long) =
    val start = System.nanoTime()
    val result = f
    (result, (System.nanoTime() - start) / 1000000L)

  private def session(): SparkSession =
    SparkSession.builder()
      .master("local[4]")
      .appName("hudi-cow-mor")
      .config("spark.ui.enabled", "false")
      .config("spark.sql.shuffle.partitions", "4")
      .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
      .config("spark.kryo.registrator", "org.apache.spark.HoodieSparkKryoRegistrar")
      .config("spark.sql.extensions", "org.apache.spark.sql.hudi.HoodieSparkSessionExtension")
      .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.hudi.catalog.HoodieCatalog")
      .getOrCreate()

  private def measure(spark: SparkSession, table: HudiTable, name: String, writeMs: Long): (Step, Seq[CategoryTotal], Option[Seq[CategoryTotal]]) =
    val (snap, snapMs) = timed(Orders.aggregate(table.snapshot(spark)))
    val ro = Option.when(table.kind == TableKind.Mor)(timed(Orders.aggregate(table.readOptimized(spark))))
    val step = Step(
      name,
      writeMs,
      snapMs,
      snap.map(_.orders).sum,
      ro.map(_._2),
      ro.map(_._1.map(_.orders).sum),
      Storage.stats(Paths.get(table.path))
    )
    println(s"${table.kind.label} $name write=${writeMs}ms snapshot=${snapMs}ms ro=${ro.map(_._2)} storage=${step.storage}")
    (step, snap, ro.map(_._1))

  private def runTable(spark: SparkSession, table: HudiTable, orders: DataFrame, batches: Seq[DataFrame]): Run =
    val (_, insertMs) = timed(table.write(orders, "insert", SaveMode.Overwrite))
    val first = measure(spark, table, "insert", insertMs)
    val upserts = batches.zipWithIndex.map { (batch, i) =>
      val (_, ms) = timed(table.write(batch, "upsert", SaveMode.Append))
      measure(spark, table, s"upsert ${i + 1}", ms)
    }
    val last = upserts.last
    val base = Map("snapshot" -> last._2) ++ last._3.map("read_optimized" -> _)
    if table.kind == TableKind.Mor then
      val (_, compactMs) = timed(table.compact(spark))
      val compacted = measure(spark, table, "compaction", compactMs)
      Run(
        (first +: upserts :+ compacted).map(_._1),
        base ++ Map("snapshot_after_compaction" -> compacted._2) ++ compacted._3.map("read_optimized_after_compaction" -> _)
      )
    else Run((first +: upserts).map(_._1), base)

  private def warmUp(spark: SparkSession, lake: Path, base: DataFrame): Unit =
    val orders = Orders.expand(base, 1)
    TableKind.values.foreach { kind =>
      val table = HudiTable(kind, lake.resolve(s"warmup_${kind.label}").toAbsolutePath.toString)
      table.write(orders, "insert", SaveMode.Overwrite)
      table.write(Orders.upsertBatch(orders, 1), "upsert", SaveMode.Append)
      Orders.aggregate(table.snapshot(spark))
      Storage.deleteRecursively(Paths.get(table.path))
    }

  private def resultJson(spark: SparkSession, rows: Long, updates: Seq[Long], cow: Run, mor: Run): String =
    val cowSnap = cow.snapshots("snapshot")
    val morSnap = mor.snapshots("snapshot")
    val morRo = mor.snapshots("read_optimized")
    val morSnapAfter = mor.snapshots("snapshot_after_compaction")
    val morRoAfter = mor.snapshots("read_optimized_after_compaction")
    Json.obj(
      "versions" -> Json.obj(
        "hudi" -> Json.str(env("HUDI_VERSION", "")),
        "spark" -> Json.str(spark.version),
        "scala" -> Json.str(env("SCALA_VERSION", "")),
        "java" -> Json.str(System.getProperty("java.version"))
      ),
      "rows" -> rows.toString,
      "copies" -> Copies.toString,
      "batchUpdates" -> Json.arr(updates.map(_.toString)),
      "tables" -> Json.obj(
        "cow" -> Json.arr(cow.steps.map(_.json)),
        "mor" -> Json.arr(mor.steps.map(_.json))
      ),
      "aggregates" -> Json.obj(
        "cow_snapshot" -> Json.totals(cowSnap),
        "mor_snapshot_before_compaction" -> Json.totals(morSnap),
        "mor_read_optimized_before_compaction" -> Json.totals(morRo),
        "mor_snapshot_after_compaction" -> Json.totals(morSnapAfter),
        "mor_read_optimized_after_compaction" -> Json.totals(morRoAfter)
      ),
      "checks" -> Json.obj(
        "cow_equals_mor_snapshot" -> (cowSnap == morSnap).toString,
        "mor_snapshot_unchanged_by_compaction" -> (morSnap == morSnapAfter).toString,
        "mor_read_optimized_equals_snapshot_after_compaction" -> (morRoAfter == morSnapAfter).toString,
        "mor_read_optimized_stale_before_compaction" -> (morRo != morSnap).toString
      )
    )

  def main(args: Array[String]): Unit =
    val lake = Paths.get(env("LAKE_DIR", "lake")).toAbsolutePath
    val results = Paths.get(env("RESULTS_DIR", "results")).toAbsolutePath
    Storage.deleteRecursively(lake)
    Files.createDirectories(lake)
    Files.createDirectories(results)
    val spark = session()
    spark.sparkContext.setLogLevel("WARN")
    try
      val base = Orders.load(spark, env("ORDERS_CSV", "data/orders.csv")).cache()
      warmUp(spark, lake, base)
      val orders = Orders.expand(base, Copies).cache()
      val rows = orders.count()
      val batches = (1 to Batches).map(b => Orders.upsertBatch(orders, b).cache())
      val updates = batches.map(_.count())
      println(s"orders=$rows updates=$updates")
      val cow = runTable(spark, HudiTable(TableKind.Cow, lake.resolve("orders_cow").toString), orders, batches)
      val mor = runTable(spark, HudiTable(TableKind.Mor, lake.resolve("orders_mor").toString), orders, batches)
      val json = resultJson(spark, rows, updates, cow, mor)
      Files.writeString(results.resolve("results.json"), json)
      println(s"wrote ${results.resolve("results.json")}")
    finally spark.stop()
