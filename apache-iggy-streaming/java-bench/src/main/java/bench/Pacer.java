package bench;

public final class Pacer {

    private Pacer() {
    }

    public static int due(double elapsedSeconds, int rate, long sent, int cap) {
        if (rate <= 0) {
            return cap;
        }
        long target = (long) (elapsedSeconds * rate) - sent;
        return (int) Math.max(0, Math.min(target, cap));
    }
}
