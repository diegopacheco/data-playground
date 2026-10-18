package eos;

import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

public final class Seeder {
    public static void main(String[] args) throws Exception {
        List<NewTopic> topics = new ArrayList<>();
        for (String scenario : Settings.SCENARIOS) {
            topics.add(new NewTopic(Settings.in(scenario), 1, (short) 1));
            topics.add(new NewTopic(Settings.out(scenario), 1, (short) 1));
        }
        try (Admin admin = Admin.create(Settings.client())) {
            admin.createTopics(topics).all().get();
        }
        List<String> payments = Files.readAllLines(Settings.DATA);
        try (KafkaProducer<String, String> producer = new KafkaProducer<>(Settings.producer())) {
            for (String scenario : Settings.SCENARIOS) {
                for (String line : payments.subList(1, payments.size())) {
                    int comma = line.indexOf(',');
                    producer.send(new ProducerRecord<>(Settings.in(scenario), line.substring(0, comma), line.substring(comma + 1)));
                }
            }
        }
        System.out.println("seeded " + (payments.size() - 1) + " payments into " + Settings.SCENARIOS.size() + " input topics");
    }
}
