package producer;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class S3ObjectStore implements ObjectStore {

    private static final String REGION = "us-east-1";
    private static final DateTimeFormatter AMZ_DATE = DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'");

    private final ProducerSettings settings;
    private final HttpClient http = HttpClient.newHttpClient();

    public S3ObjectStore(ProducerSettings settings) {
        this.settings = settings;
    }

    @Override
    public void createBucket() {
        int status = send("/" + settings.bucket(), new byte[0], "application/octet-stream");
        if (status != 200 && status != 409) {
            throw new IllegalStateException("create bucket " + settings.bucket() + " failed with HTTP " + status);
        }
    }

    @Override
    public void put(String key, byte[] body, String contentType) {
        int status = send("/" + settings.bucket() + "/" + key, body, contentType);
        if (status != 200) {
            throw new IllegalStateException("put " + key + " failed with HTTP " + status);
        }
    }

    private int send(String path, byte[] body, String contentType) {
        URI uri = URI.create(settings.endpoint() + path);
        String host = uri.getPort() < 0 ? uri.getHost() : uri.getHost() + ":" + uri.getPort();
        String amzDate = ZonedDateTime.now(ZoneOffset.UTC).format(AMZ_DATE);
        String payloadHash = hex(sha256(body));
        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("x-amz-date", amzDate)
                .header("x-amz-content-sha256", payloadHash)
                .header("content-type", contentType)
                .header("authorization", authorization("PUT", path, host, payloadHash, amzDate))
                .PUT(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        try {
            return http.send(request, HttpResponse.BodyHandlers.discarding()).statusCode();
        } catch (Exception e) {
            throw new IllegalStateException("request to " + uri + " failed", e);
        }
    }

    String authorization(String method, String path, String host, String payloadHash, String amzDate) {
        String date = amzDate.substring(0, 8);
        String scope = date + "/" + REGION + "/s3/aws4_request";
        String signedHeaders = "host;x-amz-content-sha256;x-amz-date";
        String canonical = method + "\n" + path + "\n\n"
                + "host:" + host + "\n"
                + "x-amz-content-sha256:" + payloadHash + "\n"
                + "x-amz-date:" + amzDate + "\n\n"
                + signedHeaders + "\n" + payloadHash;
        String toSign = "AWS4-HMAC-SHA256\n" + amzDate + "\n" + scope + "\n"
                + hex(sha256(canonical.getBytes(StandardCharsets.UTF_8)));
        byte[] key = hmac(("AWS4" + settings.secretKey()).getBytes(StandardCharsets.UTF_8), date);
        key = hmac(key, REGION);
        key = hmac(key, "s3");
        key = hmac(key, "aws4_request");
        String signature = hex(hmac(key, toSign));
        return "AWS4-HMAC-SHA256 Credential=" + settings.accessKey() + "/" + scope
                + ", SignedHeaders=" + signedHeaders + ", Signature=" + signature;
    }

    private static byte[] sha256(byte[] data) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(data);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static byte[] hmac(byte[] key, String data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static String hex(byte[] data) {
        return HexFormat.of().formatHex(data);
    }
}
