package bench;

import java.math.BigInteger;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicBoolean;
import org.apache.iggy.client.blocking.tcp.IggyTcpClient;
import org.apache.iggy.consumergroup.Consumer;
import org.apache.iggy.identifier.StreamId;
import org.apache.iggy.identifier.TopicId;
import org.apache.iggy.message.Message;
import org.apache.iggy.message.MessageHeader;
import org.apache.iggy.message.MessageId;
import org.apache.iggy.message.Partitioning;
import org.apache.iggy.message.PolledMessages;
import org.apache.iggy.message.PollingStrategy;
import org.apache.iggy.message.PollOptions;
import org.apache.iggy.topic.Durability;
import org.apache.iggy.topic.TopicOptions;

public final class IggyBench implements BrokerBench {

    private static final String USERNAME = "iggy";
    private static final String PASSWORD = "iggy";
    private static final StreamId STREAM = StreamId.of(BenchConfig.STREAM);
    private static final PollOptions POLL = PollOptions.waitFor(Duration.ofMillis(100))
            .withCount(1000)
            .withMaxBytes(4 * 1024 * 1024);

    @Override
    public Outcome run(BenchConfig cfg) throws Exception {
        TopicId topic = TopicId.of(cfg.topic());
        try (IggyTcpClient producerClient = connect(cfg.address())) {
            createTopic(producerClient, cfg);
            Recorder recorder = new Recorder(cfg.partitions(), Payload.nowUs() + cfg.warmupMicros(), 1);
            AtomicBoolean stop = new AtomicBoolean();
            List<IggyTcpClient> consumers = new ArrayList<>();
            List<Thread> threads = new ArrayList<>();
            for (int p = 0; p < cfg.partitions(); p++) {
                IggyTcpClient client = connect(cfg.address());
                int partition = p;
                consumers.add(client);
                threads.add(Thread.ofVirtual().start(() -> consume(client, topic, partition, recorder, stop)));
            }
            ProducerOutcome producer = produce(producerClient, topic, cfg);
            BrokerBench.drain(recorder, producer.sent(), cfg.drainSeconds());
            stop.set(true);
            for (Thread thread : threads) {
                thread.join();
            }
            consumers.forEach(IggyTcpClient::close);
            return new Outcome(producer, recorder);
        }
    }

    private static IggyTcpClient connect(String address) {
        String[] hostPort = address.split(":");
        return IggyTcpClient.builder()
                .host(hostPort[0])
                .port(Integer.parseInt(hostPort[1]))
                .credentials(USERNAME, PASSWORD)
                .shutdownQuietPeriod(Duration.ZERO)
                .buildAndLogin();
    }

    private static void createTopic(IggyTcpClient client, BenchConfig cfg) {
        if (client.streams().getStream(STREAM).isEmpty()) {
            client.streams().createStream(BenchConfig.STREAM);
        }
        TopicOptions options = TopicOptions.builder().durability(Durability.REPLICATED).build();
        client.topics().createTopic(STREAM, cfg.topic(), cfg.partitions(), options);
    }

    static Message message(byte[] payload) {
        MessageHeader header = new MessageHeader(BigInteger.ZERO, MessageId.serverGenerated(), BigInteger.ZERO,
                BigInteger.ZERO, BigInteger.ZERO, 0L, (long) payload.length, BigInteger.ZERO);
        return new Message(header, payload, Map.of());
    }

    private static ProducerOutcome produce(IggyTcpClient client, TopicId topic, BenchConfig cfg) {
        long startedAtUs = Payload.nowUs();
        long begin = System.nanoTime();
        long sent = 0;
        double elapsed;
        while ((elapsed = (System.nanoTime() - begin) / 1e9) < cfg.seconds()) {
            int count = Pacer.due(elapsed, cfg.rate(), sent, cfg.batchCap());
            if (count == 0) {
                BrokerBench.pause();
                continue;
            }
            Map<Long, List<Message>> groups = new TreeMap<>();
            for (long seq = sent; seq < sent + count; seq++) {
                groups.computeIfAbsent(seq % cfg.partitions(), k -> new ArrayList<>())
                        .add(message(Payload.encode(seq, Payload.nowUs(), cfg.size())));
            }
            for (Map.Entry<Long, List<Message>> group : groups.entrySet()) {
                client.messages().sendMessages(STREAM, topic, Partitioning.partitionId(group.getKey()), group.getValue());
            }
            sent += count;
        }
        return new ProducerOutcome(sent, 0, startedAtUs, Payload.nowUs());
    }

    private static void consume(IggyTcpClient client, TopicId topic, int partition, Recorder recorder, AtomicBoolean stop) {
        PollingStrategy strategy = PollingStrategy.offset(BigInteger.ZERO);
        Consumer consumer = Consumer.of(1L);
        while (!stop.get()) {
            PolledMessages polled = client.messages().pollMessages(STREAM, topic, partition, consumer, strategy, POLL);
            long receivedAtUs = Payload.nowUs();
            for (Message message : polled.messages()) {
                recorder.observe(partition, message.payload(), message.header().timestamp().longValue(), receivedAtUs);
            }
            if (!polled.messages().isEmpty()) {
                strategy = polled.continuation().orElseThrow();
            }
        }
    }
}
