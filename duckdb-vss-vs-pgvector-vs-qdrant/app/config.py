import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, ".run")
with open(os.path.join(ROOT, "scripts", "ports.env")) as f:
    PORTS = {k: int(v) for k, v in (line.strip().split("=") for line in f if "=" in line)}

SEED = 9
ROWS = 100000
DIM = 128
CLUSTERS = 200
SPREAD = 0.5
QUERIES = 1000
FILTERED_QUERIES = 200
WARMUP = 50
K = 10
M = 16
EF_CONSTRUCTION = 128
EF_SEARCH = [10, 40, 100, 200]
FILTERED_EF = 100
BUCKETS = 10
BUCKET = 3
BUILD_THREADS = 2
