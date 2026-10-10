ThisBuild / scalaVersion := "3.7.4"
ThisBuild / organization := "com.github.diegopacheco"

val sparkVersion = "4.2.0"
val deltaVersion = "4.4.0"
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

lazy val job = project
  .in(file("job"))
  .settings(
    name := "delta-job",
    fork := true,
    run / baseDirectory := (ThisBuild / baseDirectory).value,
    javaOptions ++= sparkOpens :+ "-Xmx768m",
    libraryDependencies ++= Seq(
      ("org.apache.spark" %% "spark-sql" % sparkVersion).cross(CrossVersion.for3Use2_13),
      "io.delta" % "delta-spark_4.2_2.13" % deltaVersion,
      "org.apache.hadoop" % "hadoop-aws" % hadoopVersion
    )
  )

lazy val ui = project
  .in(file("ui"))
  .settings(
    name := "delta-ui",
    fork := true,
    run / baseDirectory := (ThisBuild / baseDirectory).value,
    javaOptions += "-Xmx128m"
  )
