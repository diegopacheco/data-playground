package ledger;

import com.tigerbeetle.AccountBatch;
import com.tigerbeetle.Client;
import com.tigerbeetle.CreateAccountResultBatch;
import com.tigerbeetle.CreateAccountStatus;
import com.tigerbeetle.CreateTransferResultBatch;
import com.tigerbeetle.CreateTransferStatus;
import com.tigerbeetle.IdBatch;
import com.tigerbeetle.TransferBatch;
import com.tigerbeetle.UInt128;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

public final class Ledger implements AutoCloseable {

    public record NewAccount(long id, int ledger, int code) {
    }

    public record NewTransfer(long id, long debit, long credit, long amount, int ledger, int code) {
    }

    public record Balance(long id, long debitsPosted, long creditsPosted) {
    }

    public record Outcome(long created, long existing, int batches) {
    }

    private final Client client;

    private Ledger(Client client) {
        this.client = client;
    }

    public static Ledger connect() {
        return new Ledger(new Client(UInt128.asBytes(0), new String[]{Settings.TB_ADDRESS}));
    }

    public static long idOf(String key) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(key.getBytes(StandardCharsets.UTF_8));
            long id = ByteBuffer.wrap(hash).getLong() & Long.MAX_VALUE;
            return id == 0 ? 1 : id;
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    public Outcome createAccounts(List<NewAccount> accounts) throws InterruptedException {
        long created = 0;
        long existing = 0;
        int batches = 0;
        for (int from = 0; from < accounts.size(); from += Settings.BATCH_SIZE) {
            List<NewAccount> chunk = accounts.subList(from, Math.min(from + Settings.BATCH_SIZE, accounts.size()));
            AccountBatch batch = new AccountBatch(chunk.size());
            for (NewAccount a : chunk) {
                batch.add();
                batch.setId(a.id());
                batch.setLedger(a.ledger());
                batch.setCode(a.code());
            }
            CreateAccountResultBatch results = client.createAccounts(batch);
            if (results.getLength() != chunk.size()) {
                throw new IllegalStateException("expected " + chunk.size() + " account results, got " + results.getLength());
            }
            while (results.next()) {
                CreateAccountStatus status = results.getStatus();
                if (status == CreateAccountStatus.Created) {
                    created++;
                } else if (status == CreateAccountStatus.Exists) {
                    existing++;
                } else {
                    throw new IllegalStateException("account rejected: " + status);
                }
            }
            batches++;
        }
        return new Outcome(created, existing, batches);
    }

    public Outcome createTransfers(List<NewTransfer> transfers, int inFlight) {
        long created = 0;
        long existing = 0;
        int batches = 0;
        ArrayDeque<CompletableFuture<CreateTransferResultBatch>> pending = new ArrayDeque<>();
        for (int from = 0; from < transfers.size(); from += Settings.BATCH_SIZE) {
            List<NewTransfer> chunk = transfers.subList(from, Math.min(from + Settings.BATCH_SIZE, transfers.size()));
            pending.add(client.createTransfersAsync(toBatch(chunk)));
            batches++;
            if (pending.size() >= inFlight) {
                long[] counts = count(pending.poll().join());
                created += counts[0];
                existing += counts[1];
            }
        }
        while (!pending.isEmpty()) {
            long[] counts = count(pending.poll().join());
            created += counts[0];
            existing += counts[1];
        }
        if (created + existing != transfers.size()) {
            throw new IllegalStateException("expected " + transfers.size() + " transfer results, got " + (created + existing));
        }
        return new Outcome(created, existing, batches);
    }

    public Map<Long, Balance> lookup(List<Long> ids) throws InterruptedException {
        Map<Long, Balance> balances = new HashMap<>();
        for (int from = 0; from < ids.size(); from += Settings.BATCH_SIZE) {
            IdBatch batch = new IdBatch(Math.min(Settings.BATCH_SIZE, ids.size() - from));
            ids.subList(from, Math.min(from + Settings.BATCH_SIZE, ids.size())).forEach(batch::add);
            AccountBatch accounts = client.lookupAccounts(batch);
            while (accounts.next()) {
                long id = accounts.getId(UInt128.LeastSignificant);
                balances.put(id, new Balance(id,
                        accounts.getDebitsPosted().longValueExact(),
                        accounts.getCreditsPosted().longValueExact()));
            }
        }
        return balances;
    }

    private static TransferBatch toBatch(List<NewTransfer> chunk) {
        TransferBatch batch = new TransferBatch(chunk.size());
        for (NewTransfer t : chunk) {
            batch.add();
            batch.setId(t.id());
            batch.setDebitAccountId(t.debit());
            batch.setCreditAccountId(t.credit());
            batch.setAmount(t.amount());
            batch.setLedger(t.ledger());
            batch.setCode(t.code());
        }
        return batch;
    }

    private static long[] count(CreateTransferResultBatch results) {
        long created = 0;
        long existing = 0;
        while (results.next()) {
            CreateTransferStatus status = results.getStatus();
            if (status == CreateTransferStatus.Created) {
                created++;
            } else if (status == CreateTransferStatus.Exists) {
                existing++;
            } else {
                throw new IllegalStateException("transfer rejected: " + status);
            }
        }
        return new long[]{created, existing};
    }

    @Override
    public void close() {
        client.close();
    }
}
