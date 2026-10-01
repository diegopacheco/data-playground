import csv
import json
import sys

path, first, last = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
with open(path, newline="") as f:
    rows = list(csv.DictReader(f))
for row in rows[first - 1:last]:
    print(json.dumps(row, separators=(",", ":")))
