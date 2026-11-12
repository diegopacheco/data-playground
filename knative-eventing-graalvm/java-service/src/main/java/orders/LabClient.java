package orders;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

@Component
public class LabClient {

    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private final JsonMapper json;
    private final URI recordsUri;

    public LabClient(JsonMapper json, @Value("${lab.url}") String labUrl) {
        this.json = json;
        this.recordsUri = URI.create(labUrl + "/records");
    }

    public void report(HandledRecord record) {
        HttpRequest request = HttpRequest.newBuilder(recordsUri)
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(record)))
                .build();
        try {
            HttpResponse<Void> response = http.send(request, HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() != 204) {
                throw new IllegalStateException("lab answered " + response.statusCode() + " for " + record.id());
            }
        } catch (IOException e) {
            throw new IllegalStateException("lab unreachable for " + record.id(), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted while reporting " + record.id(), e);
        }
    }
}
