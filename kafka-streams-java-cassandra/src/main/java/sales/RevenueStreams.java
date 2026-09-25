package sales;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.Materialized;

import java.util.Properties;
import java.util.concurrent.CountDownLatch;

public class RevenueStreams {

    public static void main(String[] args) throws Exception {
        CqlSession session = Cassandra.connect();
        PreparedStatement upsert = session.prepare(
                "INSERT INTO sales.revenue_by_category (category, total_orders, total_quantity, total_revenue) VALUES (?, ?, ?, ?)");

        StreamsBuilder builder = new StreamsBuilder();
        builder.stream(Settings.TOPIC, Consumed.with(Serdes.String(), Serdes.String()))
                .groupBy((orderId, line) -> Totals.category(line), Grouped.with(Serdes.String(), Serdes.String()))
                .aggregate(
                        Totals.EMPTY::encode,
                        (category, line, acc) -> Totals.decode(acc).add(line).encode(),
                        Materialized.with(Serdes.String(), Serdes.String()))
                .toStream()
                .foreach((category, encoded) -> {
                    Totals t = Totals.decode(encoded);
                    session.execute(upsert.bind(category, t.orders(), t.quantity(), t.revenue()));
                    System.out.println("upsert " + category + " " + t);
                });

        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "p3-revenue-by-category");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, Settings.KAFKA);
        props.put(StreamsConfig.COMMIT_INTERVAL_MS_CONFIG, 1000);
        props.put(StreamsConfig.REPLICATION_FACTOR_CONFIG, 1);
        props.put(StreamsConfig.STATE_DIR_CONFIG, Settings.STATE_DIR);
        props.put("auto.offset.reset", "earliest");

        KafkaStreams streams = new KafkaStreams(builder.build(), props);
        CountDownLatch done = new CountDownLatch(1);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            streams.close();
            session.close();
            done.countDown();
        }));
        streams.start();
        done.await();
    }
}
