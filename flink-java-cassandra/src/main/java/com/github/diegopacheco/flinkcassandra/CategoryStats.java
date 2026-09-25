package com.github.diegopacheco.flinkcassandra;

public record CategoryStats(String category, long totalOrders, long totalQuantity, double totalRevenue) {

    public static CategoryStats fromCsvLine(String line) {
        String[] f = line.split(",");
        long quantity = Long.parseLong(f[4].trim());
        double price = Double.parseDouble(f[5].trim());
        return new CategoryStats(f[3].trim(), 1, quantity, quantity * price);
    }

    public CategoryStats merge(CategoryStats other) {
        return new CategoryStats(category, totalOrders + other.totalOrders, totalQuantity + other.totalQuantity, totalRevenue + other.totalRevenue);
    }

    public CategoryStats rounded() {
        return new CategoryStats(category, totalOrders, totalQuantity, Math.round(totalRevenue * 100.0) / 100.0);
    }
}
