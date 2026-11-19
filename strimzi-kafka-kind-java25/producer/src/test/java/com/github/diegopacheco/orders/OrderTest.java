package com.github.diegopacheco.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.Set;
import java.util.stream.LongStream;
import org.junit.jupiter.api.Test;

class OrderTest {

    @Test
    void keysAreUniqueWithinARunSoTheConsumerCanDetectLossByCountingDistinctKeys() {
        Set<String> keys = new HashSet<>();
        LongStream.range(0, 10_000).forEach(seq -> keys.add(Order.of("r1", seq).key()));
        assertEquals(10_000, keys.size());
    }

    @Test
    void keysDifferAcrossRunsSoOldRunsNeverInflateANewRunCount() {
        assertNotEquals(Order.of("r1", 7).key(), Order.of("r2", 7).key());
    }

    @Test
    void jsonCarriesTheRunIdTheConsumerGroupsBy() {
        String json = Order.of("run-9", 3).toJson();
        assertEquals("{\"runId\":\"run-9\",\"seq\":3,\"sku\":\"sku-3\",\"qty\":4,\"priceCents\":211}", json);
    }

    @Test
    void ordersAlwaysHaveAPositiveQuantityAndPrice() {
        LongStream.range(0, 1_000).mapToObj(seq -> Order.of("r", seq)).forEach(order -> {
            assertTrue(order.qty() >= 1 && order.qty() <= 5);
            assertTrue(order.priceCents() >= 100 && order.priceCents() < 10_000);
        });
    }
}
