#!/usr/bin/env bash
# Smoke-test public, list-style Worker APIs. No credentials are required.
set -euo pipefail

base_url="${1:-https://kr-realestate.joark-stock.workers.dev}"
base_url="${base_url%/}"

endpoints=(
  '/api/health'
  '/api/regions'
  '/api/cheongyak'
  '/api/development'
  '/api/evaluation'
  '/api/evaluation/weights'
)

for endpoint in "${endpoints[@]}"; do
  printf 'Checking %s%s\n' "$base_url" "$endpoint"
  curl --fail --silent --show-error "$base_url$endpoint" >/dev/null
done

printf 'Remote Worker smoke checks passed.\n'
