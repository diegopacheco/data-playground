package sales;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Properties;

public class OrdersProducer {

    public static void main(String[] args) throws Exception {
        List<String> rows = Files.readAllLines(Path.of(Settings.CSV)).stream()
                .skip(1)
                .filter(line -> !line.isBlank())
                .toList();
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, Settings.KAFKA);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        try (KafkaProducer<String, String> producer = new KafkaProducer<>(props)) {
            for (String row : rows) {
                producer.send(new ProducerRecord<>(Settings.TOPIC, row.split(",")[0], row)).get();
            }
        }
        System.out.println("produced " + rows.size() + " orders to topic " + Settings.TOPIC);
    }
}
