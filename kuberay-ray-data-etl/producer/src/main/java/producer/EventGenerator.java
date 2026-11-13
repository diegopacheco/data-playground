package producer;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public final class EventGenerator {

    static final List<String> CATEGORIES = List.of("Books", " games", "MUSIC", "food ", "Travel", "books", "GAMES ");
    static final int USERS = 500;

    private EventGenerator() {
    }

    public static List<Event> generate(String batchId, int file, int count, long ts) {
        Random random = new Random((batchId + "/" + file).hashCode());
        List<Event> events = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            events.add(new Event(
                    batchId + "-" + file + "-" + i,
                    batchId,
                    "user-" + random.nextInt(USERS),
                    CATEGORIES.get(random.nextInt(CATEGORIES.size())),
                    random.nextInt(-1000, 20000),
                    ts));
        }
        return events;
    }

    public static String toJsonLines(List<Event> events) {
        StringBuilder out = new StringBuilder();
        for (Event event : events) {
            out.append(event.toJson()).append('\n');
        }
        return out.toString();
    }
}
