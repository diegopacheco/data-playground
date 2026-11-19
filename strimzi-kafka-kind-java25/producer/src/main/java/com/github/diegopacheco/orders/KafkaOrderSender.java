package com.github.diegopacheco.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class KafkaOrderSender implements OrderSender {

    private final KafkaTemplate<String, String> template;
    private final String topic;

    public KafkaOrderSender(KafkaTemplate<String, String> template, @Value("${orders.topic}") String topic) {
        this.template = template;
        this.topic = topic;
    }

    @Override
    public void send(Order order) throws Exception {
        template.send(topic, order.key(), order.toJson()).get();
    }
}
