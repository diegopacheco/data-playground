package orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Locale;
import org.junit.jupiter.api.Test;

class TransformTest {

    @Test
    void totalIsQuantityTimesUnitPriceSoEveryVariantBillsTheSameAmount() {
        ProcessedOrder order = Transform.apply(new OrderEvent("o-1", " ab-12 ", 3, 1250));
        assertEquals(new ProcessedOrder("o-1", "AB-12", 3750), order);
    }

    @Test
    void skuIsNormalizedIndependentOfTheServerLocale() {
        Locale previous = Locale.getDefault();
        Locale.setDefault(Locale.forLanguageTag("tr-TR"));
        try {
            assertEquals("TITLE-I", Transform.apply(new OrderEvent("o-2", "title-i", 1, 1)).sku());
        } finally {
            Locale.setDefault(previous);
        }
    }

    @Test
    void invalidOrdersFailSoTheSourceRetriesInsteadOfRecordingGarbage() {
        assertThrows(IllegalArgumentException.class, () -> Transform.apply(new OrderEvent("o-3", "x", 0, 10)));
        assertThrows(IllegalArgumentException.class, () -> Transform.apply(new OrderEvent("o-4", "x", 1, -1)));
        assertThrows(IllegalArgumentException.class, () -> Transform.apply(new OrderEvent(" ", "x", 1, 1)));
    }

    @Test
    void overflowingTotalsAreRejectedInsteadOfWrappingNegative() {
        assertThrows(ArithmeticException.class,
                () -> Transform.apply(new OrderEvent("o-5", "x", Integer.MAX_VALUE, Long.MAX_VALUE / 2)));
    }
}
