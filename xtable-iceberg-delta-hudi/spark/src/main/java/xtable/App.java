package xtable;

import org.apache.spark.sql.SparkSession;

public final class App {

    private App() {
    }

    public static void main(String[] args) throws Exception {
        String step = args.length == 0 ? "" : args[0];
        switch (step) {
            case "write" -> withSpark("i8-write-hudi", WriteHudi::run);
            case "read" -> withSpark("i8-read-all", ReadAll::run);
            case "files" -> LakeFiles.run(args[1]);
            default -> throw new IllegalArgumentException("usage: write | read | files <label>");
        }
    }

    private static void withSpark(String name, Job job) throws Exception {
        SparkSession spark = Spark.session(name);
        try {
            job.run(spark);
        } finally {
            spark.stop();
        }
    }

    @FunctionalInterface
    private interface Job {
        void run(SparkSession spark) throws Exception;
    }
}
