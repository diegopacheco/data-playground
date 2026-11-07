import threading
import time as clock

import pathway as pw


class LiveTable:
    def __init__(self, table, columns):
        self.columns = columns
        self.rows = {}
        self.pending = []
        self.lock = threading.Lock()
        self.updated_at = 0.0
        self.batches = 0
        pw.io.subscribe(table, on_change=self.on_change, on_time_end=self.on_time_end)

    def on_change(self, key, row, time, is_addition):
        self.pending.append((key, {c: row[c] for c in self.columns}, is_addition))

    def on_time_end(self, time):
        changes, self.pending = self.pending, []
        with self.lock:
            for key, _, is_addition in changes:
                if not is_addition:
                    self.rows.pop(key, None)
            for key, row, is_addition in changes:
                if is_addition:
                    self.rows[key] = row
            self.updated_at = clock.time()
            self.batches += 1

    def snapshot(self):
        with self.lock:
            return {"rows": list(self.rows.values()), "updated_at": self.updated_at, "batches": self.batches}
