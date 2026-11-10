package clicks;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.LongStream;
import org.junit.jupiter.api.Test;

class ClickGeneratorTest {

    @Test
    void theSameSequenceNumberAlwaysBelongsToTheSameUserSoReplaysAreDeterministic() {
        ClickGenerator generator = new ClickGenerator(10);
        assertEquals(generator.map(1234L), new ClickGenerator(10).map(1234L));
        assertEquals(new Click("user-4", 1234L), generator.map(1234L));
    }

    @Test
    void usersAreVisitedRoundRobinSoEveryKeyGetsClicks() {
        Set<String> users = LongStream.range(0, 10).mapToObj(s -> ClickGenerator.userFor(s, 10)).collect(Collectors.toSet());
        assertEquals(10, users.size());
    }

    @Test
    void zeroUsersIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> new ClickGenerator(0));
    }
}
