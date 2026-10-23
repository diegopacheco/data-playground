ThisBuild / scalaVersion := "3.7.4"
ThisBuild / organization := "com.github.diegopacheco"

val sparkVersion = "4.1.3"
val icebergVersion = "1.11.0"
val hadoopVersion = "3.5.0"
val trinoVersion = "483"

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
  "--sun-misc-unsafe-memory-access=allow",
  "-Djdk.reflect.useDirectMethodHandle=false",
  "-Dio.netty.tryReflectionSetAccessible=true"
)

lazy val app = project
  .in(file("app"))
  .settings(
    name := "polaris-shared-catalog",
    fork := true,
    javaOptions ++= sparkOpens :+ "-Xmx512m",
    libraryDependencies ++= Seq(
      ("org.apache.spark" %% "spark-sql" % sparkVersion).cross(CrossVersion.for3Use2_13),
      "org.apache.iceberg" % "iceberg-spark-runtime-4.1_2.13" % icebergVersion,
      "org.apache.iceberg" % "iceberg-aws-bundle" % icebergVersion,
      "io.trino" % "trino-jdbc" % trinoVersion
    ),
    dependencyOverrides ++= Seq(
      "org.apache.hadoop" % "hadoop-client-api" % hadoopVersion,
      "org.apache.hadoop" % "hadoop-client-runtime" % hadoopVersion
    )
  )
