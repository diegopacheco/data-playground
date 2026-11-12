import os
import time
from pathlib import Path

STARTTIME_AFTER_COMM = 19
CGROUP_MEMORY = Path("/sys/fs/cgroup/memory.current")


def started_at_ms(proc_self_stat: str, proc_uptime: str, now_ms: int, ms_per_tick: float) -> int:
    after_comm = proc_self_stat[proc_self_stat.rindex(")") + 2 :]
    start_ticks = int(after_comm.split(" ")[STARTTIME_AFTER_COMM])
    uptime_ms = round(float(proc_uptime.split()[0]) * 1000)
    return now_ms - (uptime_ms - round(start_ticks * ms_per_tick))


def rss_kb(proc_self_status: str) -> int:
    for line in proc_self_status.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.removeprefix("VmRSS:").split()[0])
    return -1


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def process_started_at_ms() -> int:
    ms_per_tick = 1000 / os.sysconf("SC_CLK_TCK")
    stat = Path("/proc/self/stat").read_text()
    uptime = Path("/proc/uptime").read_text()
    return started_at_ms(stat, uptime, now_ms(), ms_per_tick)


def current_rss_kb() -> int:
    return rss_kb(Path("/proc/self/status").read_text())


def cgroup_memory_bytes() -> int:
    return int(CGROUP_MEMORY.read_text().strip()) if CGROUP_MEMORY.exists() else -1
