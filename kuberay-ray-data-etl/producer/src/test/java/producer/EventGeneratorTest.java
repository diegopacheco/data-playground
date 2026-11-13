package producer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class EventGeneratorTest {

    @Test
    void rewritingTheSameBatchProducesTheSameEventsSoAProducerRetryIsIdempotent() {
        assertEquals(EventGenerator.generate("s1-000001", 0, 100, 5), EventGenerator.generate("s1-000001", 0, 100, 5));
        assertNotEquals(EventGenerator.generate("s1-000001", 0, 100, 5), EventGenerator.generate("s1-000001", 1, 100, 5));
    }

    @Test
    void eventsCarryDirtyValuesTheEtlTransformHasToCleanUp() {
        List<Event> events = EventGenerator.generate("s1-000001", 0, 2000, 5);
        assertTrue(events.stream().anyMatch(e -> e.amountCents() <= 0), "no invalid amounts to filter");
        assertTrue(events.stream().anyMatch(e -> !e.category().equals(e.category().strip().toLowerCase())),
                "no unnormalized categories");
        assertEquals(2000, events.stream().map(Event::eventId).distinct().count());
    }

    @Test
    void jsonLineHasTheFieldsTheEtlReads() {
        Event event = new Event("s1-000001-0-3", "s1-000001", "user-7", " games", -12, 99);
        assertEquals("{\"event_id\":\"s1-000001-0-3\",\"batch_id\":\"s1-000001\",\"user_id\":\"user-7\","
                + "\"category\":\" games\",\"amount_cents\":-12,\"ts\":99}", event.toJson());
    }
}
