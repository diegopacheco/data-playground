package beam;

import org.apache.beam.sdk.Pipeline;
import org.apache.beam.sdk.io.TextIO;
import org.apache.beam.sdk.io.jdbc.JdbcIO;
import org.apache.beam.sdk.options.PipelineOptionsFactory;
import org.apache.beam.sdk.values.KV;

public class RevenuePipeline {

  static final String UPSERT = """
      INSERT INTO revenue_by_category (category, total_orders, total_quantity, total_revenue)
      VALUES (?, ?, ?, ?)
      ON CONFLICT (category) DO UPDATE SET
        total_orders = EXCLUDED.total_orders,
        total_quantity = EXCLUDED.total_quantity,
        total_revenue = EXCLUDED.total_revenue
      """;

  public static void main(String[] args) {
    String input = Env.get("INPUT", "data/orders.csv");
    Pipeline pipeline = Pipeline.create(PipelineOptionsFactory.fromArgs(args).withValidation().create());
    pipeline
        .apply("ReadCsv", TextIO.read().from(input))
        .apply("RevenueByCategory", new RevenueByCategory())
        .apply("WritePostgres", JdbcIO.<KV<String, Totals>>write()
            .withDataSourceConfiguration(JdbcIO.DataSourceConfiguration
                .create("org.postgresql.Driver", Env.jdbcUrl())
                .withUsername(Env.jdbcUser())
                .withPassword(Env.jdbcPassword()))
            .withStatement(UPSERT)
            .withPreparedStatementSetter((row, st) -> {
              st.setString(1, row.getKey());
              st.setLong(2, row.getValue().orders());
              st.setLong(3, row.getValue().quantity());
              st.setBigDecimal(4, row.getValue().revenue());
            }));
    pipeline.run().waitUntilFinish();
    System.out.println("beam pipeline wrote revenue_by_category from " + input);
  }
}
