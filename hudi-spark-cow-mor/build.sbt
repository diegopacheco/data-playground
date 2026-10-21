ThisBuild / scalaVersion := "3.7.4"
ThisBuild / organization := "com.github.diegopacheco"

val sparkVersion = "4.1.3"
val hudiVersion = "1.2.1"
val hadoopVersion = "3.5.0"

val sparkOpens = Seq(
  "--add-opens=java.base/java.lang=ALL-UNNAMED",
  "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED",
  "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
  "--add-opens=java.base/java.io=ALL-UNNAMED",
  "--add-opens=java.base/java.net=ALL-UNNAMED",
  "--add-opens=java.base/java.nio=ALL-UNNAMED",
  "--add-opens=java.base/java.util=ALL-UNNAMED",
  "--add-opens=java.base/java.util.concurrent=ALL-UNNAMED",
  "--add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED",
  "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED",
  "--add-opens=java.base/sun.nio.cs=ALL-UNNAMED",
  "--add-opens=java.base/sun.security.action=ALL-UNNAMED",
  "--add-opens=java.base/sun.util.calendar=ALL-UNNAMED",
  "--enable-native-access=ALL-UNNAMED",
  "-Djdk.reflect.useDirectMethodHandle=false",
  "-Dio.netty.tryReflectionSetAccessible=true"
)

lazy val dist = taskKey[Unit]("copies the runtime jars into the dist folder")

lazy val bench = project
  .in(file("bench"))
  .settings(
    name := "hudi-bench",
    fork := true,
    run / baseDirectory := (ThisBuild / baseDirectory).value,
    javaOptions ++= sparkOpens :+ "-Xmx1g",
    envVars ++= Map("HUDI_VERSION" -> hudiVersion, "SCALA_VERSION" -> scalaVersion.value),
    libraryDependencies ++= Seq(
      ("org.apache.spark" %% "spark-sql" % sparkVersion).cross(CrossVersion.for3Use2_13),
      "org.apache.hudi" % "hudi-spark4.1-bundle_2.13" % hudiVersion
    ),
    dependencyOverrides ++= Seq(
      "org.apache.hadoop" % "hadoop-client-api" % hadoopVersion,
      "org.apache.hadoop" % "hadoop-client-runtime" % hadoopVersion
    )
  )

lazy val ui = project
  .in(file("ui"))
  .settings(
    name := "hudi-ui",
    fork := true,
    run / baseDirectory := (ThisBuild / baseDirectory).value,
    dist := {
      val converter = fileConverter.value
      val out = baseDirectory.value / "dist"
      IO.delete(out)
      (Runtime / fullClasspathAsJars).value.foreach { entry =>
        val jar = converter.toPath(entry.data).toFile
        IO.copyFile(jar, out / jar.getName)
      }
    }
  )
