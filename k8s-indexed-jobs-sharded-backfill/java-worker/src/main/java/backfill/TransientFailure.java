package backfill;

public class TransientFailure extends RuntimeException {

    public TransientFailure(String message) {
        super(message);
    }
}
