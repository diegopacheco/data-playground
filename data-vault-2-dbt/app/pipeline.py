import json
import os
import subprocess
import sys
from vault import DB, ROOT, load_dates

DBT = os.path.join(ROOT, ".venv", "bin", "dbt")
PROJECT = os.path.join(ROOT, "dbt")
LOGS = os.path.join(ROOT, ".run", "logs")


def build(load_date):
    run = subprocess.run(
        [DBT, "build", "--project-dir", PROJECT, "--profiles-dir", PROJECT, "--vars", json.dumps({"load_date": load_date})],
        cwd=PROJECT, env={**os.environ, "VAULT_DB": DB}, capture_output=True, text=True)
    with open(os.path.join(LOGS, f"dbt-{load_date}.log"), "w") as f:
        f.write(run.stdout + run.stderr)
    summary = [line for line in run.stdout.splitlines() if "PASS=" in line]
    print(f"load {load_date}: {summary[-1].split('Done. ')[-1] if summary else 'no summary'}")
    if run.returncode != 0:
        sys.exit(f"dbt build failed for {load_date}, see .run/logs/dbt-{load_date}.log")


if __name__ == "__main__":
    os.makedirs(LOGS, exist_ok=True)
    dates = sys.argv[1:]
    if not dates:
        for path in (DB, DB + ".wal"):
            if os.path.exists(path):
                os.remove(path)
        dates = load_dates()
    for load_date in dates:
        build(load_date)
