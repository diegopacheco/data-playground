package bench;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) throws Exception {
        BenchConfig cfg = BenchConfig.fromEnv(System.getenv());
        BrokerBench bench = cfg.broker().equals("iggy") ? new IggyBench() : new KafkaBench();
        BrokerBench.Outcome outcome = bench.run(cfg);
        System.out.println(Result.render(Result.build(cfg, outcome, Payload.nowUs())));
        System.out.flush();
        System.exit(0);
    }
}
