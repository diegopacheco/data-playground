scalaVersion := "3.7.4"

name := "spark-scala-cassandra"

libraryDependencies ++= Seq(
  ("org.apache.spark" %% "spark-sql" % "4.2.0").cross(CrossVersion.for3Use2_13),
  ("com.datastax.spark" %% "spark-cassandra-connector" % "3.5.1").cross(CrossVersion.for3Use2_13),
  "joda-time" % "joda-time" % "2.14.4"
)

lazy val writeClasspath = taskKey[Unit]("writes the runtime classpath to the classpath file")

writeClasspath := {
  val converter = fileConverter.value
  val jars = (Runtime / fullClasspathAsJars).value.map(entry => converter.toPath(entry.data).toAbsolutePath.toString)
  IO.write(baseDirectory.value / "classpath", jars.mkString(java.io.File.pathSeparator))
}
