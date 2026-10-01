package xtable;

import org.apache.spark.sql.SparkSession;

final class Spark {

    private Spark() {
    }

    static SparkSession session(String name) {
        return SparkSession.builder()
                .appName(name)
                .master("local[2]")
                .config("spark.ui.enabled", "false")
                .config("spark.driver.host", "localhost")
                .config("spark.sql.shuffle.partitions", "2")
                .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
                .config("spark.sql.extensions", "org.apache.spark.sql.hudi.HoodieSparkSessionExtension,io.delta.sql.DeltaSparkSessionExtension")
                .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
                .config("spark.sql.catalog.default_iceberg", "org.apache.iceberg.spark.SparkCatalog")
                .config("spark.sql.catalog.default_iceberg.type", "hadoop")
                .config("spark.sql.catalog.default_iceberg.warehouse", "/tmp/iceberg-warehouse")
                .getOrCreate();
    }
}
