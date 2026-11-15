package com.github.diegopacheco.pipelinelag;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.util.HashSet;
import java.util.Set;
import java.util.stream.LongStream;
import org.junit.jupiter.api.Test;

class OrderTest {

    @Test
    void idsAreUniqueWithinARunSoEverySinkRowMapsToExactlyOneTrace() {
        Set<String> ids = new HashSet<>();
        LongStream.range(0, 10_000).forEach(seq -> ids.add(Order.of("r1", seq, 0).id()));
        assertEquals(10_000, ids.size());
    }

    @Test
    void idsDifferAcrossRunsSoOldRunsNeverMixIntoANewRunLagSample() {
        assertNotEquals(Order.of("r1", 7, 0).id(), Order.of("r2", 7, 0).id());
    }

    @Test
    void jsonCarriesTheEventTimeTheConsumerMeasuresLagFrom() {
        String json = Order.of("run-9", 3, 1_700_000_000_123L).toJson();
        assertEquals("{\"id\":\"run-9-3\",\"runId\":\"run-9\",\"seq\":3,\"sku\":\"sku-3\",\"qty\":4,\"priceCents\":211,\"eventTimeMs\":1700000000123}", json);
    }
}
