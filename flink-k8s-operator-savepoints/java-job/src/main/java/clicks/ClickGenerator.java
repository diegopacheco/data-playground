package clicks;

import org.apache.flink.connector.datagen.source.GeneratorFunction;

public final class ClickGenerator implements GeneratorFunction<Long, Click> {

    private final int users;

    public ClickGenerator(int users) {
        if (users < 1) {
            throw new IllegalArgumentException("users must be at least 1");
        }
        this.users = users;
    }

    public static String userFor(long seq, int users) {
        return "user-" + Math.floorMod(seq, users);
    }

    @Override
    public Click map(Long seq) {
        return new Click(userFor(seq, users), seq);
    }
}
