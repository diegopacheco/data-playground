package com.github.diegopacheco.pipelinelag;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class RunRegistryTest {

    private final RunRegistry registry = new RunRegistry(order -> { });

    @Test
    void reusingARunIdIsRejectedSoTwoRunsNeverShareMessageIds() throws Exception {
        assertTrue(registry.start("once", 10).isPresent());
        assertTrue(registry.start("once", 10).isEmpty());
        registry.stop("once");
    }

    @Test
    void runIdsThatWouldBreakTheJsonPayloadAreRejected() {
        assertThrows(IllegalArgumentException.class, () -> registry.start("bad\"id", 10));
        assertThrows(IllegalArgumentException.class, () -> registry.start("", 10));
    }

    @Test
    void ratesOutsideTheSupportedRangeAreRejected() {
        assertThrows(IllegalArgumentException.class, () -> registry.start("zero", 0));
        assertThrows(IllegalArgumentException.class, () -> registry.start("huge", 1_000_000));
    }
}
