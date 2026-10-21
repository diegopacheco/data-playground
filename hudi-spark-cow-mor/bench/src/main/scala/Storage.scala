import java.nio.file.{Files, Path}
import scala.jdk.CollectionConverters.*
import scala.util.Using

final case class StorageStats(baseFiles: Int, logFiles: Int, baseBytes: Long, logBytes: Long, otherFiles: Int, otherBytes: Long):
  def dataBytes: Long = baseBytes + logBytes
  def totalBytes: Long = dataBytes + otherBytes

object Storage:

  private def isMeta(root: Path, file: Path): Boolean =
    root.relativize(file).iterator().asScala.exists(_.toString == ".hoodie")

  def stats(root: Path): StorageStats =
    val files = Using.resource(Files.walk(root))(_.iterator().asScala.filter(Files.isRegularFile(_)).toList)
    val (data, other) = files.partition { f =>
      val name = f.getFileName.toString
      !isMeta(root, f) && !name.endsWith(".crc") && (name.endsWith(".parquet") || name.contains(".log."))
    }
    val (base, logs) = data.partition(_.getFileName.toString.endsWith(".parquet"))
    def bytes(fs: List[Path]): Long = fs.map(Files.size).sum
    StorageStats(base.size, logs.size, bytes(base), bytes(logs), other.size, bytes(other))

  def deleteRecursively(root: Path): Unit =
    if Files.exists(root) then
      Using.resource(Files.walk(root))(_.iterator().asScala.toList).reverse.foreach(Files.delete)
