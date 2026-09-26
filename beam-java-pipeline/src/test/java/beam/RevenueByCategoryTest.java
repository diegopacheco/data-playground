package beam;

import java.util.List;
import org.apache.beam.sdk.testing.PAssert;
import org.apache.beam.sdk.testing.TestPipeline;
import org.apache.beam.sdk.transforms.Create;
import org.apache.beam.sdk.values.KV;
import org.apache.beam.sdk.values.PCollection;
import org.junit.Rule;
import org.junit.Test;

public class RevenueByCategoryTest {

  @Rule
  public final transient TestPipeline pipeline = TestPipeline.create();

  private PCollection<KV<String, Totals>> run(String... lines) {
    return pipeline.apply(Create.of(List.of(lines))).apply(new RevenueByCategory());
  }

  @Test
  public void revenueIsQuantityTimesPriceSummedPerCategoryAndHeaderIsNotAnOrder() {
    PCollection<KV<String, Totals>> out = run(
        RevenueByCategory.HEADER,
        "1,ana,Book A,books,2,10.50,2026-08-01 10:00:00",
        "2,bob,Book B,books,1,4.25,2026-08-01 11:00:00",
        "3,cid,Ball,sports,3,20.00,2026-08-01 12:00:00");
    PAssert.that(out).containsInAnyOrder(
        KV.of("books", new Totals(2, 3, 2525)),
        KV.of("sports", new Totals(1, 3, 6000)));
    pipeline.run().waitUntilFinish();
  }

  @Test
  public void revenueIsExactInCentsWhereDoubleArithmeticWouldDrift() {
    PCollection<KV<String, Totals>> out = run(
        "1,ana,Pen,office,1,0.10,2026-08-01 10:00:00",
        "2,bob,Pen,office,1,0.20,2026-08-01 11:00:00",
        "3,cid,Pen,office,1,0.10,2026-08-01 12:00:00");
    PAssert.that(out).containsInAnyOrder(KV.of("office", new Totals(3, 3, 40)));
    pipeline.run().waitUntilFinish();
  }

  @Test
  public void categoryCaseAndSpacesDoNotSplitTheSameCategory() {
    PCollection<KV<String, Totals>> out = run(
        "1,ana,Lamp,Home ,1,15.00,2026-08-01 10:00:00",
        "2,bob,Rug,home,2,5.00,2026-08-01 11:00:00",
        "");
    PAssert.that(out).containsInAnyOrder(KV.of("home", new Totals(2, 3, 2500)));
    pipeline.run().waitUntilFinish();
  }
}
