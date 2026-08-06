#!/usr/bin/env bash
# Apply every checked-in D1 migration. Remote use requires explicit confirmation.
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
      echo "Refusing remote migration: set CONFIRM_REMOTE_D1=1." >&2
      exit 1
    }
    D1_TARGET=(--remote)
    ;;
  *) usage ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATABASE_NAME="${D1_DATABASE_NAME:-kr-realestate}"

shopt -s nullglob
migrations=("$WORKER_DIR"/migrations/*.sql)
(( ${#migrations[@]} > 0 )) || {
  echo "No migration files found in $WORKER_DIR/migrations" >&2
  exit 1
}

for migration in "${migrations[@]}"; do
  echo "Applying $(basename "$migration") to $TARGET D1 database $DATABASE_NAME"
  (
    cd "$WORKER_DIR"
    npx wrangler d1 execute "$DATABASE_NAME" "${D1_TARGET[@]}" --file="$migration"
  )
done
