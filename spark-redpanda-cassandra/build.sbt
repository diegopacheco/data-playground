ThisBuild / scalaVersion := "3.7.4"
ThisBuild / organization := "com.github.diegopacheco"

val sparkVersion = "4.2.0"

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
    name := "revenue-job",
    fork := true,
    javaOptions ++= sparkOpens :+ "-Xmx1g",
    libraryDependencies ++= Seq(
      ("org.apache.spark" %% "spark-sql" % sparkVersion).cross(CrossVersion.for3Use2_13),
      ("org.apache.spark" %% "spark-sql-kafka-0-10" % sparkVersion).cross(CrossVersion.for3Use2_13),
      ("com.datastax.spark" %% "spark-cassandra-connector" % "3.5.1").cross(CrossVersion.for3Use2_13),
      "joda-time" % "joda-time" % "2.14.4"
    )
  )

lazy val ui = project
  .in(file("ui"))
  .settings(
    name := "revenue-ui",
    fork := true,
    libraryDependencies += "org.apache.cassandra" % "java-driver-core" % "4.19.3"
  )
