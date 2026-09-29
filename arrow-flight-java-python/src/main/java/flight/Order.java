package flight;

public record Order(long orderId, String customer, String product, String category, int quantity, double price, String ts) {

    public static Order parse(String line) {
        String[] c = line.split(",", -1);
        return new Order(Long.parseLong(c[0]), c[1], c[2], c[3], Integer.parseInt(c[4]), Double.parseDouble(c[5]), c[6]);
    }

    public Order withId(long id) {
        return new Order(id, customer, product, category, quantity, price, ts);
    }

    public String toCsv() {
        return orderId + "," + customer + "," + product + "," + category + "," + quantity + "," + price + "," + ts;
    }
}
