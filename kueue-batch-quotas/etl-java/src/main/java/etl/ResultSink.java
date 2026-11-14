package etl;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.stream.Collectors;

public final class ResultSink {

    private final EtlSettings settings;

    public ResultSink(EtlSettings settings) {
        this.settings = settings;
    }

    public Path markStarted(long startedAtMs) throws IOException {
        return Files.writeString(jobDir().resolve(settings.podName() + ".started"), Long.toString(startedAtMs));
    }

    public Path write(String json) throws IOException {
        Path target = jobDir().resolve(settings.podName() + ".json");
        Path tmp = jobDir().resolve(settings.podName() + ".tmp");
        Files.writeString(tmp, json);
        return Files.move(tmp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }

    public String row(Summary summary, long startedAtMs, long finishedAtMs) {
        String totals = summary.totals().entrySet().stream()
                .map(e -> "\"" + e.getKey() + "\":" + e.getValue())
                .collect(Collectors.joining(",", "{", "}"));
        return "{\"job\":\"" + settings.jobName() + "\",\"team\":\"" + settings.team()
                + "\",\"worker\":\"java\",\"pod\":\"" + settings.podName()
                + "\",\"rows\":" + summary.rows() + ",\"seed\":" + settings.seed()
                + ",\"rounds\":" + settings.rounds() + ",\"digest\":\"" + summary.digest()
                + "\",\"totals\":" + totals + ",\"started_at_ms\":" + startedAtMs
                + ",\"finished_at_ms\":" + finishedAtMs + "}";
    }

    private Path jobDir() throws IOException {
        return Files.createDirectories(settings.resultsDir().resolve(settings.jobName()));
    }
}
