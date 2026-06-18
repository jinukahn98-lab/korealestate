#!/bin/bash
set -e

echo "=== Checking database tables ==="

DB_FILE="realestate.db"

TABLES_EXIST=$(python3 -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('${DB_FILE}')
    cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'external_%'\")
    rows = cur.fetchall()
    conn.close()
    print('yes' if rows else 'no')
except Exception as e:
    print('no')
")

if [ "$TABLES_EXIST" = "no" ]; then
    echo "=== Seeding external_data tables ==="
    python3 -c "
import sys
sys.path.insert(0, '.')
from strategy.autopilot import Autopilot
ap = Autopilot()
ap.run_full_pipeline()
ap.close()
"
    echo "=== Seeding complete ==="
else
    echo "=== external_data tables already exist, skipping seed ==="
fi

echo "=== Starting Streamlit ==="
exec streamlit run app_v3.py \
    --server.port=7860 \
    --server.address=0.0.0.0
