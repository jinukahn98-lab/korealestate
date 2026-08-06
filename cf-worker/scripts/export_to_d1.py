#!/usr/bin/env python3
"""
export_to_d1.py — Extract aggregated data from local realestate.db + wiki_rag.db
into a Cloudflare D1-compatible seed.sql file.

Outputs INSERT statements for:
  Full-copy tables (from realestate.db):
    - scorer_results        (~78 rows)
    - ml_weights            (~14 rows)
    - external_cheongyak    (~662 rows)
    - external_development  (~136 rows)
    - daily_eval_log        (~14 rows)
  Aggregated table (from apt_trade + apt_rent, since 2024-01-01):
    - monthly_stats         (per region x year_month: avg_price, trade_count,
                             avg_jeonse_deposit, jeonse_rate)
  Wiki tables (from wiki_rag.db):
    - wiki_docs             (path, title, category, date_token, content, indexed_at)
    - wiki_fts              (FTS5 virtual table mirror)

Usage:
    python3 cf-worker/scripts/export_to_d1.py

Output:
    cf-worker/seed.sql
"""

import argparse
import subprocess
import sqlite3
import sys
from pathlib import Path

# --- Paths (resolved relative to this script so cwd does not matter) ---------
# script: <project>/cf-worker/scripts/export_to_d1.py
PROJECT = Path(__file__).resolve().parents[2]
RE_DB = PROJECT / "realestate.db"
WIKI_DB = PROJECT / "wiki_rag.db"
SEED_SQL = PROJECT / "cf-worker" / "seed.sql"
D1_SYNC_DIR = PROJECT / "cf-worker" / "d1_sync"
DRIVE_DATA_REMOTE = "gdrive:cf-worker-drive-sync/kr-realestate-data"

# These are the only local datasets copied to D1.  Raw apt_trade and apt_rent
# records are used solely to produce monthly_stats and are never emitted.
PUBLIC_TABLES = (
    "scorer_results",
    "ml_weights",
    "external_cheongyak",
    "external_development",
    "daily_eval_log",
    "monthly_stats",
    "wiki_search",
    "wiki_fts",
)

# --- Value formatting --------------------------------------------------------

# Per-column truncation limits (in characters).
TRUNC = {
    "scorer_results": {"factors": None},          # keep full JSON
    "daily_eval_log": {"result_json": 5000},
    "wiki_docs": {"content": 5000},
}


def sql_val(v, truncate=None):
    """Format a Python value as a SQL literal for D1/SQLite.

    - None  -> NULL
    - float -> trimmed decimal (NULL if NaN)
    - int   -> integer literal
    - str   -> 'escaped' (single quotes doubled), optionally truncated
    """
    if v is None:
        return "NULL"
    # bool is a subclass of int; normalise first
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:  # NaN
            return "NULL"
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s if s else "0"
    # everything else -> string literal
    s = str(v)
    if truncate and len(s) > truncate:
        s = s[:truncate]
    s = s.replace("'", "''")
    # also neutralise NUL bytes which break SQLite
    s = s.replace("\x00", "")
    # Placeholder chars must not survive in data
    s = s.replace("\x01", "").replace("\x02", "")
    if "\n" in s or "\r" in s:
        # Keep every statement on a single line: raw newlines inside strings
        # desync the D1 exec()/wrangler statement splitter (both treat each
        # line as a statement boundary). Restore at insert time via
        # replace(char(1)->\n, char(2)->\r) — same trick as sync_to_d1.py.
        s = s.replace("\r", "\x02").replace("\n", "\x01")
        return f"replace(replace('{s}', char(1), char(10)), char(2), char(13))"
    return f"'{s}'"


def build_insert(table, columns, row, truncate_map=None):
    """Render one INSERT statement for a row (a sqlite3.Row or tuple)."""
    truncate_map = truncate_map or {}
    vals = []
    for i, col in enumerate(columns):
        v = row[i]
        vals.append(sql_val(v, truncate_map.get(col)))
    col_list = ", ".join(columns)
    val_list = ", ".join(vals)
    return f"INSERT INTO {table} ({col_list}) VALUES ({val_list});"


def connect_row(db_path):
    """Open a read-only sqlite connection with Row factory."""
    if not db_path.exists():
        sys.exit(f"[ERROR] database not found: {db_path}")
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# --- Section exporters -------------------------------------------------------

def export_table(conn, out, chunks, table, columns, order_by=None, where=None):
    """Full-copy export of a table using the given column subset/order."""
    col_sql = ", ".join(columns)
    sql = f"SELECT {col_sql} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    rows = conn.execute(sql).fetchall()
    truncate_map = TRUNC.get(table, {})
    out.write(f"-- {table} ({len(rows)} rows)\n")
    chunk_lines = [f"DELETE FROM {table};"]
    for r in rows:
        stmt = build_insert(table, columns, r, truncate_map)
        out.write(stmt + "\n")
        chunk_lines.append(stmt)
    out.write("\n")
    chunks[table] = chunk_lines
    return len(rows)


def export_monthly_stats(conn, out, chunks):
    """Aggregate apt_trade + apt_rent into monthly_stats since 2024-01-01."""
    sql = """
        WITH trade_agg AS (
            SELECT region,
                   substr(deal_date, 1, 7) AS year_month,
                   ROUND(AVG(price) / 10000.0, 2) AS avg_price,
                   COUNT(*) AS trade_count
            FROM apt_trade
            WHERE deal_date >= '2024-01-01' AND region IS NOT NULL
            GROUP BY region, year_month
        ),
        rent_agg AS (
            -- 전세 (jeonse) = deposit-only lease. The apt_rent.rent_type column
            -- is unpopulated (NULL) for all rows in the current DB, so we
            -- identify 전세 two ways: explicit rent_type='전세' when present,
            -- OR the standard heuristic (rent_type unset AND no monthly rent,
            -- i.e. rent=0) which is how deposit-only leases are recorded.
            SELECT region,
                   substr(deal_date, 1, 7) AS year_month,
                   ROUND(AVG(deposit) / 10000.0, 2) AS avg_jeonse_deposit
            FROM apt_rent
            WHERE (rent_type = '전세'
                   OR (COALESCE(rent_type, '') = '' AND COALESCE(rent, 0) = 0))
              AND deal_date >= '2024-01-01'
              AND region IS NOT NULL
            GROUP BY region, year_month
        )
        SELECT t.region,
               t.year_month,
               t.avg_price,
               t.trade_count,
               r.avg_jeonse_deposit,
               CASE
                   WHEN t.avg_price IS NOT NULL AND t.avg_price > 0
                        AND r.avg_jeonse_deposit IS NOT NULL
                   THEN ROUND(r.avg_jeonse_deposit * 100.0 / t.avg_price, 2)
                   ELSE NULL
               END AS jeonse_rate
        FROM trade_agg t
        LEFT JOIN rent_agg r
               ON t.region = r.region AND t.year_month = r.year_month
        ORDER BY t.region, t.year_month
    """
    rows = conn.execute(sql).fetchall()
    columns = ["region", "year_month", "avg_price", "trade_count",
               "avg_jeonse_deposit", "jeonse_rate"]
    out.write(f"-- monthly_stats ({len(rows)} rows, aggregated)\n")
    chunk_lines = ["DELETE FROM monthly_stats;"]
    for r in rows:
        stmt = build_insert("monthly_stats", columns, r)
        out.write(stmt + "\n")
        chunk_lines.append(stmt)
    out.write("\n")
    chunks["monthly_stats"] = chunk_lines
    return len(rows)


def export_wiki(wiki_conn, out, chunks):
    """Export wiki content into the D1 `wiki_search` table + `wiki_fts` mirror.

    Note: the D1 schema (cf-worker/schema.sql) names the base table
    `wiki_search` with columns (title, category, date_token, content,
    indexed_at) and no `path` column, even though the source wiki_rag.db
    stores rows in `wiki_docs` keyed by `path`. We therefore drop `path`
    and target `wiki_search` to stay aligned with the D1 schema.
    """
    src_cols = ["path", "title", "category", "date_token", "content",
                "indexed_at"]
    rows = wiki_conn.execute(
        f"SELECT {', '.join(src_cols)} FROM wiki_docs ORDER BY path"
    ).fetchall()
    truncate = 5000

    # D1 wiki_search columns (no path).
    search_cols = ["title", "category", "date_token", "content", "indexed_at"]
    out.write(f"-- wiki_search ({len(rows)} rows)\n")
    search_chunk = ["DELETE FROM wiki_search;"]
    for r in rows:
        content = r["content"]
        if content is not None and len(content) > truncate:
            content = content[:truncate]
        search_row = {
            "title": r["title"],
            "category": r["category"],
            "date_token": r["date_token"],
            "content": content,
            "indexed_at": r["indexed_at"],
        }
        vals = ", ".join(
            sql_val(search_row[c], truncate if c == "content" else None)
            for c in search_cols
        )
        col_list = ", ".join(search_cols)
        stmt = f"INSERT INTO wiki_search ({col_list}) VALUES ({vals});"
        out.write(stmt + "\n")
        search_chunk.append(stmt)
    out.write("\n")
    chunks["wiki_search"] = search_chunk

    # FTS5 mirror — same content (truncated) into the virtual table.
    fts_cols = ["title", "category", "content", "date_token"]
    out.write(f"-- wiki_fts ({len(rows)} rows, FTS5 mirror)\n")
    fts_chunk = ["DELETE FROM wiki_fts;"]
    for r in rows:
        content = r["content"]
        if content is not None and len(content) > truncate:
            content = content[:truncate]
        fts_row = {
            "title": r["title"],
            "category": r["category"],
            "content": content,
            "date_token": r["date_token"],
        }
        vals = ", ".join(
            sql_val(fts_row[c], truncate if c == "content" else None)
            for c in fts_cols
        )
        col_list = ", ".join(fts_cols)
        stmt = f"INSERT INTO wiki_fts ({col_list}) VALUES ({vals});"
        out.write(stmt + "\n")
        fts_chunk.append(stmt)
    out.write("\n")
    chunks["wiki_fts"] = fts_chunk
    return len(rows)


# --- Main --------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Export public aggregate data into Cloudflare D1 SQL files."
    )
    parser.add_argument("--realestate-db", type=Path, default=RE_DB)
    parser.add_argument("--wiki-db", type=Path, default=WIKI_DB)
    parser.add_argument("--output", type=Path, default=SEED_SQL)
    parser.add_argument("--split-dir", type=Path, default=D1_SYNC_DIR)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload generated per-table SQL files using rclone.",
    )
    parser.add_argument("--drive-remote", default=DRIVE_DATA_REMOTE)
    return parser.parse_args()


def main():
    args = parse_args()
    re_db = args.realestate_db.resolve()
    wiki_db = args.wiki_db.resolve()
    seed_sql = args.output.resolve()
    d1_sync_dir = args.split_dir.resolve()

    print(f"[INFO] project root : {PROJECT}")
    print(f"[INFO] realestate.db: {re_db} ({re_db.stat().st_size:,} bytes)")
    print(f"[INFO] wiki_rag.db  : {wiki_db} ({wiki_db.stat().st_size:,} bytes)")
    print(f"[INFO] output       : {seed_sql}")

    re_conn = connect_row(re_db)
    wiki_conn = connect_row(wiki_db)

    counts = {}
    chunks = {}  # table -> [DELETE stmt, INSERT stmt, ...], for the Drive per-table split
    seed_sql.parent.mkdir(parents=True, exist_ok=True)

    with open(seed_sql, "w", encoding="utf-8") as out:
        out.write("-- seed.sql — D1 seed data for kr-realestate cf-worker\n")
        out.write("-- Auto-generated by cf-worker/scripts/export_to_d1.py\n")
        out.write("-- Source: realestate.db + wiki_rag.db\n\n")

        counts["scorer_results"] = export_table(
            re_conn, out, chunks, "scorer_results",
            ["region", "total_score", "grade", "factors", "version",
             "scored_at"],
            order_by="region",
        )
        counts["ml_weights"] = export_table(
            re_conn, out, chunks, "ml_weights",
            ["factor_name", "default_weight", "optimized_weight",
             "updated_at"],
            order_by="factor_name",
        )
        counts["external_cheongyak"] = export_table(
            re_conn, out, chunks, "external_cheongyak",
            ["id", "region", "pblanc_name", "total_supply",
             "total_competition", "score_cutoff", "supply_price",
             "market_price", "pblanc_start", "pblanc_end"],
            order_by="id",
        )
        counts["external_development"] = export_table(
            re_conn, out, chunks, "external_development",
            ["id", "region", "project_name", "project_type", "status",
             "expected_completion", "impact_score"],
            order_by="id",
        )
        counts["daily_eval_log"] = export_table(
            re_conn, out, chunks, "daily_eval_log",
            ["run_date", "task", "status", "result_json", "created_at"],
            order_by="run_date, task",
        )
        counts["monthly_stats"] = export_monthly_stats(re_conn, out, chunks)
        counts["wiki_search"] = export_wiki(wiki_conn, out, chunks)
        # wiki_fts mirror counted same as wiki_search
        counts["wiki_fts"] = counts["wiki_search"]

    re_conn.close()
    wiki_conn.close()

    # --- Per-table split for Drive (see D1_SYNC_DIR / DRIVE_DATA_REMOTE) -----
    d1_sync_dir.mkdir(parents=True, exist_ok=True)
    for table, lines in chunks.items():
        (d1_sync_dir / f"{table}.sql").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] wrote {len(chunks)} per-table files to {d1_sync_dir}")

    if args.upload:
        try:
            rclone = subprocess.run(
                ["rclone", "copy", str(d1_sync_dir), args.drive_remote],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            print("[WARN] rclone is not installed; generated SQL was not uploaded")
        else:
            if rclone.returncode != 0:
                print(f"[WARN] rclone upload to {args.drive_remote} failed: {rclone.stderr.strip()}")
            else:
                print(f"[OK] uploaded per-table files to {args.drive_remote}")

    # --- Report --------------------------------------------------------------
    total_inserts = sum(
        c for k, c in counts.items() if k != "wiki_fts"
    ) + counts["wiki_fts"]
    size = seed_sql.stat().st_size

    print("\n=== Export complete ===")
    print(f"{'table':<22} {'rows':>7}")
    print("-" * 31)
    for k, v in counts.items():
        print(f"{k:<22} {v:>7}")
    print("-" * 31)
    print(f"{'TOTAL INSERTS':<22} {total_inserts:>7}")
    print(f"{'seed.sql size':<22} {size:>7} bytes ({size/1024:.1f} KiB)")
    print(f"[OK] wrote {seed_sql}")


if __name__ == "__main__":
    main()
