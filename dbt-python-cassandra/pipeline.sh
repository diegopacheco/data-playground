#!/usr/bin/env bash
set -euo pipefail
cd /app/dbt
dbt seed
dbt run
dbt test
cd /app
python app/loader.py
