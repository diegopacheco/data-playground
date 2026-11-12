package orders;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ProcessStats {

    private static final long MILLIS_PER_TICK = 10;
    private static final int STARTTIME_AFTER_COMM = 19;

    private ProcessStats() {
    }

    public static long startedAtMs(String procSelfStat, String procUptime, long nowMs) {
        String afterComm = procSelfStat.substring(procSelfStat.lastIndexOf(')') + 2);
        long startTicks = Long.parseLong(afterComm.split(" ")[STARTTIME_AFTER_COMM]);
        double uptimeSeconds = Double.parseDouble(procUptime.strip().split(" ")[0]);
        long uptimeMs = Math.round(uptimeSeconds * 1000);
        return nowMs - (uptimeMs - startTicks * MILLIS_PER_TICK);
    }

    public static long rssKb(String procSelfStatus) {
        for (String line : procSelfStatus.split("\n")) {
            if (line.startsWith("VmRSS:")) {
                return Long.parseLong(line.substring(6).strip().split(" ")[0]);
            }
        }
        return -1;
    }

    public static long processStartedAtMs() {
        return startedAtMs(read("/proc/self/stat"), read("/proc/uptime"), System.currentTimeMillis());
    }

    public static long currentRssKb() {
        return rssKb(read("/proc/self/status"));
    }

    public static long cgroupMemoryBytes() {
        Path path = Path.of("/sys/fs/cgroup/memory.current");
        return Files.exists(path) ? Long.parseLong(read(path.toString()).strip()) : -1;
    }

    private static String read(String path) {
        try {
            return Files.readString(Path.of(path));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
