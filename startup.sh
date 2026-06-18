#!/bin/bash
set -e

echo "=== HuggingFace Space Startup ==="
echo "Checking realestate.db..."

DB_FILE="realestate.db"
DB_GZ_URL="https://github.com/jinukahn98-lab/korealestate/releases/download/v1.0/realestate.db.gz"

# Step 1: Ensure realestate.db exists with apt_trade table
DB_OK=$(python3 -c "
import sqlite3, os
if not os.path.exists('$DB_FILE') or os.path.getsize('$DB_FILE') < 1000:
    print('no')
else:
    try:
        conn = sqlite3.connect('$DB_FILE')
        cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='apt_trade'\")
        print('yes' if cur.fetchone() else 'no')
        conn.close()
    except:
        print('no')
")

if [ "$DB_OK" = "no" ]; then
    echo "=== Downloading realestate.db from GitHub ==="
    curl -sL -o /tmp/realestate.db.gz "$DB_GZ_URL"
    gunzip -f /tmp/realestate.db.gz
    mv /tmp/realestate.db "$DB_FILE"
    echo "=== DB downloaded: $(ls -lh $DB_FILE | awk '{print $5}') ==="
else
    echo "=== DB exists with apt_trade table ==="
fi

# Step 2: Check and seed external data tables
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
    echo "=== External data tables already exist, skipping seed ==="
fi

echo "=== Starting Streamlit ==="
exec streamlit run app_v3.py \
    --server.port=7860 \
    --server.address=0.0.0.0
