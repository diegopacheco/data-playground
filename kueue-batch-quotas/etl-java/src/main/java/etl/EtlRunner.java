package etl;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "etl.run", havingValue = "true", matchIfMissing = true)
public class EtlRunner implements ApplicationRunner {

    private final EtlSettings settings;

    public EtlRunner(EtlSettings settings) {
        this.settings = settings;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        ResultSink sink = new ResultSink(settings);
        long started = System.currentTimeMillis();
        sink.markStarted(started);
        Summary summary = Transform.summarize(settings.rows(), settings.seed(), settings.rounds());
        var path = sink.write(sink.row(summary, started, System.currentTimeMillis()));
        System.out.println("wrote " + path + " digest=" + summary.digest());
    }
}
