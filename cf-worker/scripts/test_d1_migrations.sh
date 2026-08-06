#!/usr/bin/env bash
# Verify that the checked-in D1 schema can be applied repeatedly to local D1.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATABASE_NAME="${D1_DATABASE_NAME:-kr-realestate}"

"$SCRIPT_DIR/apply_d1_migrations.sh" local
"$SCRIPT_DIR/apply_d1_migrations.sh" local

(
  cd "$WORKER_DIR"
  npx wrangler d1 execute "$DATABASE_NAME" --local \
    --command="SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = 'monthly_stats';"
)

echo "[OK] local D1 migrations applied twice successfully"
