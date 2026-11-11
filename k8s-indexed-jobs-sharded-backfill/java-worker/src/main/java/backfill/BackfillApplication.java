package backfill;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BackfillApplication {

    @Bean
    Settings settings() {
        return Settings.fromEnv(System.getenv());
    }

    public static void main(String[] args) throws InterruptedException {
        ConfigurableApplicationContext context = SpringApplication.run(BackfillApplication.class, args);
        int code = context.getBean(BackfillRunner.class).run();
        System.exit(SpringApplication.exit(context, () -> code));
    }
}
