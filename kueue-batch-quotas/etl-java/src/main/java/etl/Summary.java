package etl;

import java.util.SequencedMap;

public record Summary(int rows, SequencedMap<String, Long> totals, String digest) {
}
