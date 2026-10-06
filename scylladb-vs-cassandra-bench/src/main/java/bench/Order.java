package bench;

import java.math.BigDecimal;

public record Order(long orderId, String customer, String product, String category, int quantity, BigDecimal price, String ts) {

    public static Order parse(String line) {
        String[] f = line.split(",");
        return new Order(Long.parseLong(f[0]), f[1], f[2], f[3], Integer.parseInt(f[4]), new BigDecimal(f[5]), f[6]);
    }

    public String csv() {
        return orderId + "," + customer + "," + product + "," + category + "," + quantity + "," + price.toPlainString() + "," + ts;
    }
}
