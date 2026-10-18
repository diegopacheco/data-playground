package eos;

import java.nio.file.Path;
import java.util.List;
import java.util.Properties;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

final class Settings {
    static final int UI_PORT = Integer.parseInt(System.getenv("UI_PORT"));
    static final int BATCH = Integer.parseInt(System.getenv("BATCH"));
    static final Path RUN = Path.of(System.getenv("RUN_DIR"));
    static final Path DATA = Path.of(System.getenv("DATA_FILE"));
    static final List<String> SCENARIOS = List.of("transactional", "at-least-once", "fencing");

    static String in(String scenario) {
        return scenario + "-in";
    }

    static String out(String scenario) {
        return scenario + "-out";
    }

    static Properties client() {
        Properties p = new Properties();
        p.put("bootstrap.servers", System.getenv("KAFKA_BOOTSTRAP"));
        return p;
    }

    static Properties producer() {
        Properties p = client();
        p.put("key.serializer", StringSerializer.class.getName());
        p.put("value.serializer", StringSerializer.class.getName());
        p.put("acks", "all");
        return p;
    }

    static Properties consumer(String isolation) {
        Properties p = client();
        p.put("key.deserializer", StringDeserializer.class.getName());
        p.put("value.deserializer", StringDeserializer.class.getName());
        p.put("isolation.level", isolation);
        p.put("enable.auto.commit", "false");
        p.put("auto.offset.reset", "earliest");
        return p;
    }
}
