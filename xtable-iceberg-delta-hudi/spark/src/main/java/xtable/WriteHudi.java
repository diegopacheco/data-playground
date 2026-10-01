package xtable;

import org.apache.spark.sql.Dataset;
import org.apache.spark.sql.Row;
import org.apache.spark.sql.SaveMode;
import org.apache.spark.sql.SparkSession;
import org.apache.spark.sql.types.DataTypes;
import org.apache.spark.sql.types.StructType;

final class WriteHudi {

    private WriteHudi() {
    }

    static StructType schema() {
        return new StructType()
                .add("order_id", DataTypes.IntegerType, false)
                .add("customer", DataTypes.StringType)
                .add("product", DataTypes.StringType)
                .add("category", DataTypes.StringType)
                .add("quantity", DataTypes.IntegerType)
                .add("price", DataTypes.createDecimalType(10, 2))
                .add("ts", DataTypes.StringType);
    }

    static void run(SparkSession spark) {
        Dataset<Row> orders = spark.read().option("header", "true").schema(schema()).csv(Paths.CSV);
        orders.write().format("hudi")
                .option("hoodie.table.name", "orders")
                .option("hoodie.datasource.write.table.type", "COPY_ON_WRITE")
                .option("hoodie.datasource.write.operation", "insert")
                .option("hoodie.datasource.write.recordkey.field", "order_id")
                .option("hoodie.datasource.write.precombine.field", "ts")
                .option("hoodie.datasource.write.partitionpath.field", "category")
                .mode(SaveMode.Overwrite)
                .save(Paths.TABLE);
        System.out.println("hudi table written rows=" + orders.count() + " path=" + Paths.TABLE);
    }
}
