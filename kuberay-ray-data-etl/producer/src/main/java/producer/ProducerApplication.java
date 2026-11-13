package producer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ProducerSettings.class)
public class ProducerApplication {

    public static void main(String[] args) {
        System.exit(SpringApplication.exit(SpringApplication.run(ProducerApplication.class, args)));
    }
}
