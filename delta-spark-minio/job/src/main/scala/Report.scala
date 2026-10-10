import java.nio.file.{Files, Path}
import org.apache.spark.sql.DataFrame

object Report:

  def quote(s: String): String =
    "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", " ") + "\""

  def rows(df: DataFrame): String = df.toJSON.collect().mkString("[", ",", "]")

  def strings(values: Seq[String]): String = values.map(quote).mkString("[", ",", "]")

  def write(dir: String, name: String, json: String): Unit =
    val out = Path.of(dir)
    Files.createDirectories(out)
    Files.writeString(out.resolve(s"$name.json"), json)
    println(s"wrote $dir/$name.json")
