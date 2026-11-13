package producer;

public interface ObjectStore {

    void createBucket();

    void put(String key, byte[] body, String contentType);
}
