package clicks;

import org.apache.flink.api.common.functions.OpenContext;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.util.Collector;

public final class ClickCounter extends KeyedProcessFunction<String, Click, String> {

    private final String job;
    private final String version;
    private transient ValueState<Long> count;

    public ClickCounter(String job, String version) {
        this.job = job;
        this.version = version;
    }

    public static String line(String job, String version, Click click, long count) {
        return "CLICKS job=" + job + " version=" + version + " user=" + click.user() + " seq=" + click.seq() + " count=" + count;
    }

    @Override
    public void open(OpenContext context) {
        count = getRuntimeContext().getState(new ValueStateDescriptor<>("count", Long.class));
    }

    @Override
    public void processElement(Click click, Context context, Collector<String> out) throws Exception {
        Long previous = count.value();
        long next = previous == null ? 1 : previous + 1;
        count.update(next);
        out.collect(line(job, version, click, next));
    }
}
