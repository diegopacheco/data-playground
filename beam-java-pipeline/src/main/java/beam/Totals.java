package beam;

import java.io.Serializable;
import java.math.BigDecimal;
import org.apache.beam.sdk.coders.DefaultCoder;
import org.apache.beam.sdk.coders.SerializableCoder;

@DefaultCoder(SerializableCoder.class)
public record Totals(long orders, long quantity, long revenueCents) implements Serializable {

  public static final Totals ZERO = new Totals(0, 0, 0);

  public static Totals ofOrder(long quantity, long priceCents) {
    return new Totals(1, quantity, quantity * priceCents);
  }

  public Totals plus(Totals other) {
    return new Totals(orders + other.orders, quantity + other.quantity, revenueCents + other.revenueCents);
  }

  public BigDecimal revenue() {
    return BigDecimal.valueOf(revenueCents, 2);
  }
}
