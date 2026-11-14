package etl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.jayway.jsonpath.JsonPath;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ResultSinkTest {

    @TempDir
    Path dir;

    EtlSettings settings(String pod) {
        return new EtlSettings("job-1", pod, "finance", 10, 7, 2, dir);
    }

    List<String> files() throws IOException {
        try (Stream<Path> s = Files.list(dir.resolve("job-1"))) {
            return s.map(p -> p.getFileName().toString()).sorted().toList();
        }
    }

    @Test
    void eachAttemptWritesItsOwnFilesSoADuplicateRunIsVisible() throws IOException {
        for (String pod : List.of("pod-a", "pod-b")) {
            ResultSink sink = new ResultSink(settings(pod));
            sink.markStarted(1);
            sink.write(sink.row(Transform.summarize(10, 7, 2), 1, 2));
        }
        assertEquals(List.of("pod-a.json", "pod-a.started", "pod-b.json", "pod-b.started"), files());
    }

    @Test
    void aKilledAttemptLeavesAStartMarkerButNoResult() throws IOException {
        new ResultSink(settings("pod-a")).markStarted(1);
        assertEquals(List.of("pod-a.started"), files());
    }

    @Test
    void resultRowHasTheSameKeysAndValuesThePythonWorkerWrites() throws IOException {
        ResultSink sink = new ResultSink(settings("pod-a"));
        Summary summary = Transform.summarize(10, 7, 2);
        String json = Files.readString(sink.write(sink.row(summary, 5, 9)));
        assertEquals("job-1", JsonPath.read(json, "$.job"));
        assertEquals("java", JsonPath.read(json, "$.worker"));
        assertEquals(10, (int) JsonPath.read(json, "$.rows"));
        assertEquals(summary.digest(), JsonPath.read(json, "$.digest"));
        assertEquals(summary.totals().get("EMEA").intValue(), (int) JsonPath.read(json, "$.totals.EMEA"));
        assertEquals(List.of("pod-a.json"), files());
    }

    @Test
    void settingsRejectEmptyWork() {
        assertThrows(IllegalArgumentException.class, () -> new EtlSettings("j", "p", "t", 0, 1, 1, dir));
    }
}
