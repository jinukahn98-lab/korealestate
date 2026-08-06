#!/usr/bin/env bash
# Apply generated public aggregate table dumps one table at a time.
set -euo pipefail

usage() {
  echo "Usage: $0 <local|remote>" >&2
  exit 64
}

[[ $# -eq 1 ]] || usage
TARGET="$1"
case "$TARGET" in
  local) D1_TARGET=(--local) ;;
  remote)
    [[ "${CONFIRM_REMOTE_D1:-}" == "1" ]] || {
      echo "Refusing remote data sync: set CONFIRM_REMOTE_D1=1." >&2
      exit 1
    }
    D1_TARGET=(--remote)
    ;;
  *) usage ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_DIR="$WORKER_DIR/d1_sync"
DATABASE_NAME="${D1_DATABASE_NAME:-kr-realestate}"

# Do not discover arbitrary SQL files here: only the exporter's public tables
# may be sent to D1. This makes an accidental raw apt_trade/apt_rent dump inert.
PUBLIC_TABLES=(
  scorer_results
  ml_weights
  external_cheongyak
  external_development
  daily_eval_log
  monthly_stats
  wiki_search
  wiki_fts
)
sql_files=()
for table in "${PUBLIC_TABLES[@]}"; do
  sql_file="$SYNC_DIR/$table.sql"
  [[ -f "$sql_file" ]] || {
    echo "Missing generated table SQL file: $sql_file. Run export_to_d1.py first." >&2
    exit 1
  }
  sql_files+=("$sql_file")
done

for sql_file in "${sql_files[@]}"; do
  echo "Syncing $(basename "$sql_file") to $TARGET D1 database $DATABASE_NAME"
  (
    cd "$WORKER_DIR"
    npx wrangler d1 execute "$DATABASE_NAME" "${D1_TARGET[@]}" --file="$sql_file"
  )
done

echo "[OK] synced ${#sql_files[@]} public aggregate table files to $TARGET D1"
