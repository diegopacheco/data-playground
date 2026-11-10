package clicks;

import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.api.connector.source.util.ratelimit.RateLimiterStrategy;
import org.apache.flink.connector.datagen.source.DataGeneratorSource;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.util.ParameterTool;

public final class ClickJob {

    private ClickJob() {
    }

    public static DataGeneratorSource<Click> source(int users, double rate) {
        return new DataGeneratorSource<>(new ClickGenerator(users), Long.MAX_VALUE, RateLimiterStrategy.perSecond(rate), TypeInformation.of(Click.class));
    }

    public static void main(String[] args) throws Exception {
        ParameterTool params = ParameterTool.fromArgs(args);
        String version = params.get("version", "v1");
        int users = params.getInt("users", 10);
        double rate = params.getDouble("rate", 20);
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.fromSource(source(users, rate), WatermarkStrategy.noWatermarks(), "clicks-source")
            .uid("clicks-source")
            .keyBy(Click::user)
            .process(new ClickCounter("java", version))
            .uid("click-counter")
            .name("click-counter")
            .print()
            .uid("clicks-print");
        env.execute("clicks-java");
    }
}
