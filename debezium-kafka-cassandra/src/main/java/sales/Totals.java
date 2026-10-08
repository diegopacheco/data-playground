package sales;

import java.math.BigDecimal;

public record Totals(String category, long orders, long quantity, BigDecimal revenue) {
}
