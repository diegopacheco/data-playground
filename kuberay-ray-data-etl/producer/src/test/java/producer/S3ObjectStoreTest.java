package producer;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class S3ObjectStoreTest {

    @Test
    void signatureMatchesAnIndependentSigV4ComputationSoMinioAcceptsThePut() {
        ProducerSettings settings = new ProducerSettings("http://minio:9000", "test-access", "test-secret", "events",
                ProducerSettings.Mode.STEADY, "s1", Duration.ofSeconds(5), 0, 1, 1);
        String header = new S3ObjectStore(settings).authorization("PUT", "/events/input/s1-000001/part-0.jsonl",
                "minio:9000", "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824", "20261107T101500Z");
        assertEquals("AWS4-HMAC-SHA256 Credential=test-access/20261107/us-east-1/s3/aws4_request, "
                + "SignedHeaders=host;x-amz-content-sha256;x-amz-date, "
                + "Signature=4d1687040ebf9b0f82b173731b6e3116d3c589afcb1072afd9d7fa2bf9d4ae47", header);
    }
}
