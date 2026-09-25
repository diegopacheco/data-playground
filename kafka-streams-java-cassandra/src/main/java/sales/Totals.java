package sales;

public record Totals(long orders, long quantity, long revenueCents) {

    public static final Totals EMPTY = new Totals(0, 0, 0);

    public Totals add(String csvLine) {
        String[] f = csvLine.split(",");
        long qty = Long.parseLong(f[4].trim());
        long priceCents = Math.round(Double.parseDouble(f[5].trim()) * 100);
        return new Totals(orders + 1, quantity + qty, revenueCents + qty * priceCents);
    }

    public double revenue() {
        return revenueCents / 100.0;
    }

    public String encode() {
        return orders + "," + quantity + "," + revenueCents;
    }

    public static Totals decode(String value) {
        String[] f = value.split(",");
        return new Totals(Long.parseLong(f[0]), Long.parseLong(f[1]), Long.parseLong(f[2]));
    }

    public static String category(String csvLine) {
        return csvLine.split(",")[3].trim();
    }
}
