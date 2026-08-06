/**
 * Pulls manual override CSVs from a Google Drive folder and mirrors them into
 * the `manual_overrides` D1 table. Runs on a Cron Trigger, so it never
 * depends on any machine other than Cloudflare's edge.
 *
 * Every run REPLACES the full table content with whatever rows are currently
 * in Drive — deleting a row (or a whole file) in Drive removes the override,
 * and the scorer-computed value applies again untouched.
 *
 * CSV format (header required): region,field,value,note
 *   region: matches scorer_results.region
 *   field:  the logical field being overridden, e.g. 'grade', 'note'
 *   value:  free text; numeric fields are parsed by whoever reads the override
 *   note:   optional human-readable justification
 */

import { getAccessToken, listFolderFiles, downloadFile, type ServiceAccountKey } from "./google-drive";

export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  GOOGLE_SERVICE_ACCOUNT_KEY: string;
  GOOGLE_DRIVE_FOLDER_ID: string;
  GOOGLE_DRIVE_DATA_FOLDER_ID: string;
}

interface OverrideRow {
  region: string;
  field: string;
  value: string;
  note: string | null;
}

function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      fields.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  fields.push(current);
  return fields.map((f) => f.trim());
}

const REQUIRED_COLUMNS = ["region", "field", "value"];

export function parseOverrideCsv(text: string, fileName: string): OverrideRow[] {
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length === 0) return [];

  const header = parseCsvLine(lines[0]).map((h) => h.toLowerCase());
  for (const col of REQUIRED_COLUMNS) {
    if (!header.includes(col)) {
      throw new Error(`missing required column "${col}" (found: ${header.join(", ")})`);
    }
  }
  const idx = Object.fromEntries(header.map((h, i) => [h, i]));

  const rows: OverrideRow[] = [];
  for (let i = 1; i < lines.length; i += 1) {
    const cols = parseCsvLine(lines[i]);
    const region = cols[idx.region]?.trim();
    const field = cols[idx.field]?.trim();
    const value = cols[idx.value]?.trim();
    const note = idx.note !== undefined ? cols[idx.note]?.trim() || null : null;
    if (!region || !field || value === undefined || value === "") {
      throw new Error(`${fileName}:${i + 1} missing a required value`);
    }
    rows.push({ region, field, value, note });
  }
  return rows;
}

async function replaceOverrides(db: D1Database, rows: OverrideRow[]): Promise<number> {
  const dedup = new Map<string, OverrideRow>();
  for (const row of rows) {
    dedup.set(`${row.region} ${row.field}`, row);
  }
  const statements = [db.prepare("DELETE FROM manual_overrides")];
  for (const row of dedup.values()) {
    statements.push(
      db
        .prepare(
          `INSERT INTO manual_overrides (region, field, value, note, updated_at)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)`
        )
        .bind(row.region, row.field, row.value, row.note)
    );
  }
  await db.batch(statements);
  return dedup.size;
}

export interface DriveSyncSummary {
  filesScanned: number;
  rowsWritten: number;
  errors: string[];
}

export async function runDriveSync(env: Env): Promise<DriveSyncSummary> {
  const key = JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_KEY) as ServiceAccountKey;
  const accessToken = await getAccessToken(key);
  const files = await listFolderFiles(accessToken, env.GOOGLE_DRIVE_FOLDER_ID);
  const csvFiles = files.filter((f) => f.name.toLowerCase().endsWith(".csv"));

  const rows: OverrideRow[] = [];
  const errors: string[] = [];
  for (const file of csvFiles) {
    try {
      const text = await downloadFile(accessToken, file.id);
      rows.push(...parseOverrideCsv(text, file.name));
    } catch (err) {
      errors.push(`${file.name}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  const written = await replaceOverrides(env.DB, rows);
  return { filesScanned: csvFiles.length, rowsWritten: written, errors };
}

export interface TableDataSyncSummary {
  filesScanned: number;
  applied: string[];
  skipped: number;
  errors: string[];
}

/**
 * Pulls per-table `.sql` dump files (one file = one table, produced by
 * cf-worker/scripts/export_to_d1.py's split output) from a second Drive
 * folder and applies each via D1's raw multi-statement exec(). This is the
 * "original data accumulates in Drive" path: the scorer/collector pipeline's
 * accumulated tables flow through Drive instead of being pushed to D1
 * directly, so the Worker's Cron Trigger — not the pipeline machine — is
 * what ultimately keeps D1 current.
 *
 * Each file must be self-contained (its own `DELETE FROM <table>;` followed
 * by that table's INSERT statements, no BEGIN/COMMIT). Only files whose
 * Drive modifiedTime changed since the last run are re-applied.
 */
export async function runTableDataSync(env: Env): Promise<TableDataSyncSummary> {
  const key = JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_KEY) as ServiceAccountKey;
  const accessToken = await getAccessToken(key);
  const files = await listFolderFiles(accessToken, env.GOOGLE_DRIVE_DATA_FOLDER_ID);
  const sqlFiles = files.filter((f) => f.name.toLowerCase().endsWith(".sql"));

  const { results: stateRows } = await env.DB.prepare(
    "SELECT file_id, modified_time FROM drive_sync_state"
  ).all<{ file_id: string; modified_time: string }>();
  const stateByFileId = new Map((stateRows ?? []).map((r) => [r.file_id, r.modified_time]));

  const applied: string[] = [];
  let skipped = 0;
  const errors: string[] = [];
  for (const file of sqlFiles) {
    if (stateByFileId.get(file.id) === file.modifiedTime) {
      skipped += 1;
      continue;
    }
    try {
      const sqlText = await downloadFile(accessToken, file.id);
      await env.DB.exec(sqlText);
      await env.DB.prepare(
        `INSERT INTO drive_sync_state (file_id, path, modified_time, updated_at)
         VALUES (?, ?, ?, CURRENT_TIMESTAMP)
         ON CONFLICT(file_id) DO UPDATE SET
           path = excluded.path, modified_time = excluded.modified_time, updated_at = CURRENT_TIMESTAMP`
      )
        .bind(file.id, file.name, file.modifiedTime)
        .run();
      applied.push(file.name);
    } catch (err) {
      errors.push(`${file.name}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return { filesScanned: sqlFiles.length, applied, skipped, errors };
}

/** Fetches overrides for a set of regions, keyed by region → {field: {value, note}}. */
export async function loadOverrides(
  db: D1Database,
  regions: string[]
): Promise<Map<string, Record<string, { value: string; note: string | null }>>> {
  if (regions.length === 0) return new Map();
  const placeholders = regions.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT region, field, value, note FROM manual_overrides WHERE region IN (${placeholders})`
    )
    .bind(...regions)
    .all<{ region: string; field: string; value: string; note: string | null }>();

  const byRegion = new Map<string, Record<string, { value: string; note: string | null }>>();
  for (const row of results ?? []) {
    if (!byRegion.has(row.region)) byRegion.set(row.region, {});
    byRegion.get(row.region)![row.field] = { value: row.value, note: row.note };
  }
  return byRegion;
}
