package etl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class TransformTest {

    static final String GOLDEN_DIGEST = "62eaacdf12ac7df3806a84e9090d10a7b6ed653cbcf941fa3667093329352ea5";
    static final Map<String, Long> GOLDEN_TOTALS = Map.of("AMER", 12701464L, "APAC", 11792576L, "EMEA", 12012574L, "LATAM", 12291279L);

    @Test
    void goldenResultIsTheCrossLanguageContractSharedWithThePythonWorker() {
        Summary summary = Transform.summarize(1000, 7, 3);
        assertEquals(GOLDEN_DIGEST, summary.digest());
        assertEquals(GOLDEN_TOTALS, Map.copyOf(summary.totals()));
        assertEquals(List.copyOf(Transform.REGIONS), List.copyOf(summary.totals().keySet()));
    }

    @Test
    void aRerunAfterPreemptionProducesTheIdenticalResult() {
        assertEquals(Transform.summarize(500, 11, 4), Transform.summarize(500, 11, 4));
    }

    @Test
    void aDifferentSeedIsADifferentDataset() {
        assertNotEquals(Transform.summarize(500, 11, 1).digest(), Transform.summarize(500, 12, 1).digest());
    }

    @Test
    void roundsOnlyAddCpuWorkAndNeverChangeTheTotals() {
        Summary light = Transform.summarize(300, 5, 1);
        Summary heavy = Transform.summarize(300, 5, 9);
        assertEquals(light.totals(), heavy.totals());
        assertNotEquals(light.digest(), heavy.digest());
    }

    @Test
    void totalsAccountForEveryGeneratedCent() {
        List<Sale> sales = Transform.generate(2000, 3).toList();
        Set<String> regions = sales.stream().map(Sale::region).collect(Collectors.toSet());
        assertEquals(Set.copyOf(Transform.REGIONS), regions);
        assertTrue(sales.stream().allMatch(s -> s.amountCents() >= 0 && s.amountCents() < Transform.MAX_AMOUNT_CENTS));
        long generated = sales.stream().mapToLong(Sale::amountCents).sum();
        long summed = Transform.summarize(2000, 3, 1).totals().values().stream().mapToLong(Long::longValue).sum();
        assertEquals(generated, summed);
    }

    @Test
    void splitmix64MatchesTheReferenceFirstOutputForSeedZero() {
        assertEquals(0xE220A8397B1DCDAFL, Transform.splitmix64(0));
    }
}
