package events;

import java.nio.file.Path;
import org.apache.spark.sql.SparkSession;

final class LocalSpark {

    private LocalSpark() {
    }

    static SparkSession withWarehouse(Path warehouse) {
        return SparkSession.builder()
                .master("local[2]")
                .appName("events-job-tests")
                .config("spark.ui.enabled", "false")
                .config("spark.sql.shuffle.partitions", "2")
                .config("spark.sql.session.timeZone", "UTC")
                .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
                .config("spark.sql.catalog.lake", "org.apache.iceberg.spark.SparkCatalog")
                .config("spark.sql.catalog.lake.type", "hadoop")
                .config("spark.sql.catalog.lake.warehouse", warehouse.toUri().toString())
                .config("spark.sql.catalog.lake.cache-enabled", "false")
                .getOrCreate();
    }
}
