#!/usr/bin/env python3
"""Regression tests for the public-only Cloudflare D1 export."""

import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
EXPORTER = PROJECT / "cf-worker" / "scripts" / "export_to_d1.py"
SCHEMA = PROJECT / "cf-worker" / "schema.sql"


class D1ExportTest(unittest.TestCase):
    def make_realestate_db(self, path: Path) -> None:
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE scorer_results (region TEXT, total_score REAL, grade TEXT, factors TEXT, version TEXT, scored_at TEXT);
            CREATE TABLE ml_weights (factor_name TEXT, default_weight REAL, optimized_weight REAL, updated_at TEXT);
            CREATE TABLE external_cheongyak (id INTEGER, region TEXT, pblanc_name TEXT, total_supply INTEGER, total_competition REAL, score_cutoff REAL, supply_price REAL, market_price REAL, pblanc_start TEXT, pblanc_end TEXT);
            CREATE TABLE external_development (id INTEGER, region TEXT, project_name TEXT, project_type TEXT, status TEXT, expected_completion TEXT, impact_score REAL);
            CREATE TABLE daily_eval_log (id INTEGER, run_date TEXT, task TEXT, status TEXT, result_json TEXT, created_at TEXT);
            CREATE TABLE apt_trade (region TEXT, deal_date TEXT, price REAL);
            CREATE TABLE apt_rent (region TEXT, deal_date TEXT, rent_type TEXT, rent REAL, deposit REAL);
            INSERT INTO scorer_results VALUES ('서울', 91.25, 'A', '{"quote":"O''Brien"}', 'v1', '2026-01-01');
            INSERT INTO ml_weights VALUES ('price', 0.5, 0.6, '2026-01-01');
            INSERT INTO external_cheongyak VALUES (1, '서울', '공고', 10, 2.5, 50, 100, 120, '2026-01-01', '2026-01-02');
            INSERT INTO external_development VALUES (1, '서울', '사업', 'rail', 'planned', '2030-01-01', 0.9);
            INSERT INTO daily_eval_log VALUES (1, '2026-01-01', 'eval', 'ok', '{"ok":true}', '2026-01-01');
            INSERT INTO apt_trade VALUES ('서울', '2025-01-15', 100000);
            INSERT INTO apt_rent VALUES ('서울', '2025-01-20', NULL, 0, 70000);
            """
        )
        conn.close()

    def make_wiki_db(self, path: Path) -> None:
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE wiki_docs (path TEXT, title TEXT, category TEXT, date_token TEXT, content TEXT, indexed_at TEXT);
            INSERT INTO wiki_docs VALUES ('guide.md', 'Guide', 'docs', '2026-01', 'line one\nline two', '2026-01-01');
            """
        )
        conn.close()

    def test_export_is_d1_safe_and_public_aggregates_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            realestate_db = tmp_path / "realestate.db"
            wiki_db = tmp_path / "wiki_rag.db"
            output = tmp_path / "seed.sql"
            split_dir = tmp_path / "split"
            self.make_realestate_db(realestate_db)
            self.make_wiki_db(wiki_db)

            result = subprocess.run(
                [
                    "python3", str(EXPORTER),
                    "--realestate-db", str(realestate_db),
                    "--wiki-db", str(wiki_db),
                    "--output", str(output),
                    "--split-dir", str(split_dir),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Export complete", result.stdout)
            sql = output.read_text(encoding="utf-8")
            self.assertNotRegex(sql, r"(?im)^\s*(BEGIN|COMMIT|PRAGMA)\b")
            self.assertNotIn("INSERT INTO apt_trade", sql)
            self.assertNotIn("INSERT INTO apt_rent", sql)
            self.assertIn("INSERT INTO monthly_stats", sql)
            self.assertIn("'서울', '2025-01', 10", sql)
            self.assertEqual(
                {path.stem for path in split_dir.glob("*.sql")},
                {
                    "scorer_results", "ml_weights", "external_cheongyak",
                    "external_development", "daily_eval_log", "monthly_stats",
                    "wiki_search", "wiki_fts",
                },
            )

            target = sqlite3.connect(":memory:")
            target.executescript(SCHEMA.read_text(encoding="utf-8"))
            target.executescript(sql)
            self.assertEqual(target.execute("SELECT COUNT(*) FROM monthly_stats").fetchone()[0], 1)
            self.assertEqual(target.execute("SELECT COUNT(*) FROM wiki_fts").fetchone()[0], 1)
            target.close()


if __name__ == "__main__":
    unittest.main()
