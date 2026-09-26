package beam;

import java.math.BigDecimal;
import java.util.Locale;
import org.apache.beam.sdk.transforms.Combine;
import org.apache.beam.sdk.transforms.DoFn;
import org.apache.beam.sdk.transforms.PTransform;
import org.apache.beam.sdk.transforms.ParDo;
import org.apache.beam.sdk.values.KV;
import org.apache.beam.sdk.values.PCollection;

public class RevenueByCategory extends PTransform<PCollection<String>, PCollection<KV<String, Totals>>> {

  public static final String HEADER = "order_id,customer,product,category,quantity,price,ts";

  @Override
  public PCollection<KV<String, Totals>> expand(PCollection<String> lines) {
    return lines
        .apply("ParseOrders", ParDo.of(new ParseOrderFn()))
        .apply("SumPerCategory", Combine.perKey(new SumTotalsFn()));
  }

  static class ParseOrderFn extends DoFn<String, KV<String, Totals>> {
    @ProcessElement
    public void process(@Element String line, OutputReceiver<KV<String, Totals>> out) {
      if (line.isBlank() || line.equals(HEADER)) {
        return;
      }
      String[] cols = line.split(",");
      String category = cols[3].trim().toLowerCase(Locale.ROOT);
      long quantity = Long.parseLong(cols[4].trim());
      long priceCents = new BigDecimal(cols[5].trim()).movePointRight(2).longValueExact();
      out.output(KV.of(category, Totals.ofOrder(quantity, priceCents)));
    }
  }

  static class SumTotalsFn extends Combine.CombineFn<Totals, Totals, Totals> {
    @Override
    public Totals createAccumulator() {
      return Totals.ZERO;
    }

    @Override
    public Totals addInput(Totals acc, Totals input) {
      return acc.plus(input);
    }

    @Override
    public Totals mergeAccumulators(Iterable<Totals> accs) {
      Totals sum = Totals.ZERO;
      for (Totals t : accs) {
        sum = sum.plus(t);
      }
      return sum;
    }

    @Override
    public Totals extractOutput(Totals acc) {
      return acc;
    }
  }
}
