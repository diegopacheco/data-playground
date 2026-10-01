package xtable;

import static org.apache.spark.sql.functions.col;
import static org.apache.spark.sql.functions.count;
import static org.apache.spark.sql.functions.input_file_name;
import static org.apache.spark.sql.functions.sum;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import org.apache.spark.sql.Dataset;
import org.apache.spark.sql.Row;
import org.apache.spark.sql.SparkSession;

final class ReadAll {

    private static final List<String> FORMATS = List.of("hudi", "delta", "iceberg");

    private ReadAll() {
    }

    static void run(SparkSession spark) throws IOException {
        List<String> summary = new ArrayList<>();
        List<String> first = null;
        List<String> firstFiles = null;
        for (String format : FORMATS) {
            long start = System.currentTimeMillis();
            Dataset<Row> table = spark.read().format(format).load(Paths.TABLE);
            List<String> aggregates = aggregates(table);
            List<String> files = dataFiles(table);
            long rows = table.count();
            long millis = System.currentTimeMillis() - start;
            Paths.write("agg_" + format + ".tsv", aggregates);
            Paths.write("datafiles_" + format + ".txt", files);
            summary.add(format + "\t" + rows + "\t" + files.size() + "\t" + millis);
            System.out.println(format + " rows=" + rows + " files=" + files.size() + " ms=" + millis);
            aggregates.forEach(line -> System.out.println("  " + line));
            if (first == null) {
                first = aggregates;
                firstFiles = files;
            } else if (!first.equals(aggregates) || !firstFiles.equals(files)) {
                throw new IllegalStateException(format + " disagrees with " + FORMATS.get(0));
            }
        }
        Paths.write("readers.tsv", summary);
        System.out.println("all readers agree on aggregates and data files");
    }

    private static List<String> aggregates(Dataset<Row> table) {
        return table.groupBy("category")
                .agg(count("*").as("orders"),
                        sum("quantity").as("units"),
                        sum(col("quantity").multiply(col("price"))).as("revenue"))
                .orderBy("category")
                .collectAsList()
                .stream()
                .map(r -> r.getString(0) + "\t" + r.getLong(1) + "\t" + r.getLong(2) + "\t" + r.getDecimal(3).setScale(2).toPlainString())
                .toList();
    }

    private static List<String> dataFiles(Dataset<Row> table) {
        return table.select(input_file_name().as("file"))
                .distinct()
                .collectAsList()
                .stream()
                .map(r -> Paths.relative(r.getString(0)))
                .sorted()
                .toList();
    }
}
