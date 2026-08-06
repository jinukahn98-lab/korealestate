#!/usr/bin/env node
/**
 * API contract tests for the kr-realestate Cloudflare Worker (Hono app).
 *
 * Runs the REAL bundled app (esbuild output of src/index.ts) in plain Node
 * with an in-memory mocked D1 binding — no network, no server, no new deps.
 * Exercises every public API endpoint and asserts the JSON contract:
 *
 *   GET /api/health            -> { status: 'ok' }
 *   GET /api/regions           -> { count: number, results: Array }
 *   GET /api/cheongyak         -> { count, limit, offset, results }
 *   GET /api/development       -> { count, results }
 *   GET /api/evaluation        -> { count, results }
 *   GET /api/search?q=...      -> { query, count, results }
 *   invalid query params       -> 400 JSON { error }
 *   uncaught handler errors    -> 500 JSON { error: 'internal_error' }
 *
 * Build the bundle first:  npm run test:api  (or npx esbuild ...)
 */
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BUNDLE = join(__dirname, '.build', 'index.mjs');
if (!existsSync(BUNDLE)) {
  console.error(`[api-test] bundle not found: ${BUNDLE}\n[api-test] run: npm run test:api (builds it first)`);
  process.exit(1);
}
const worker = (await import(BUNDLE)).default;

// ---------------------------------------------------------------------------
// Fixtures — one small row per table, enough to prove the contract shapes.
// ---------------------------------------------------------------------------
const TABLES = {
  scorer_results: [
    { region: '서울 강남구', total_score: 92.5, grade: 'A', factors: '{"a":1}', version: 'v1', scored_at: '2026-01-01' },
    { region: '경기 성남시 분당구', total_score: 88.1, grade: 'B', factors: '{}', version: 'v1', scored_at: '2026-01-01' },
  ],
  monthly_stats: [
    { region: '서울 강남구', year_month: '202601', avg_price: 100000, trade_count: 42, avg_jeonse_deposit: 60000, jeonse_rate: 60 },
  ],
  external_cheongyak: [
    { id: 1, region: '서울 강남구', pblanc_name: '강남 푸르지오', total_supply: 100, total_competition: 12.3, score_cutoff: 70, supply_price: 50000, market_price: 70000, pblanc_start: '2026-03-01', pblanc_end: '2026-03-10' },
    { id: 2, region: '경기 성남시 분당구', pblanc_name: '분당 레이크', total_supply: 50, total_competition: 8.0, score_cutoff: 65, supply_price: 40000, market_price: 55000, pblanc_start: '2026-02-01', pblanc_end: '2026-02-10' },
  ],
  external_development: [
    { id: 1, region: '서울 강남구', project_name: 'GTX-A', project_type: '교통', status: '진행중', expected_completion: '2027', impact_score: 9 },
  ],
  daily_eval_log: [
    { id: 1, run_date: '2026-08-01', task: 'score', status: 'success', result_json: '{}', created_at: '2026-08-01T00:00:00Z' },
  ],
  ml_weights: [],
  manual_overrides: [
    { region: '서울 강남구', field: 'note', value: '강세', note: null },
  ],
  wiki_fts: [
    { title: '강남구', category: '지역', date_token: '2026', content: '서울 강남구의 부동산 시장 분석' },
    { title: '분당', category: '지역', date_token: '2026', content: '성남 분당의 시세 동향' },
  ],
  drive_sync_state: [],
};

// ---------------------------------------------------------------------------
// Mocked D1 — a tiny SQL evaluator covering the exact query shapes the routes
// issue (SELECT ... WHERE col = ? / col IN (...) / MATCH ? / LIKE ?, optional
// ORDER BY + LIMIT/OFFSET, plus exec/batch/run no-ops).
// ---------------------------------------------------------------------------
function execSelect(sql, binds, tables) {
  const fromMatch = sql.match(/FROM\s+([a-zA-Z_]+)/);
  if (!fromMatch) throw new Error(`mock D1: no FROM in: ${sql}`);
  const tableName = fromMatch[1];
  if (!(tableName in tables)) throw new Error(`mock D1: unknown table "${tableName}"`);
  let rows = tables[tableName];
  let bindIdx = 0;

  const whereMatch = sql.match(/WHERE\s+(.*?)(?:\s+ORDER BY|\s+LIMIT|$)/s);
  if (whereMatch) {
    const where = whereMatch[1].trim();
    if (/MATCH\s+\?/.test(where)) {
      const q = String(binds[bindIdx++]).toLowerCase();
      rows = rows.filter((r) => Object.values(r).some((v) => String(v ?? '').toLowerCase().includes(q)));
    } else if (/IN\s*\(/.test(where)) {
      const colMatch = where.match(/(\w+)\s+IN/);
      const n = (where.match(/\?/g) || []).length;
      const values = binds.slice(bindIdx, bindIdx + n).map(String);
      bindIdx += n;
      rows = rows.filter((r) => values.includes(String(r[colMatch[1]])));
    } else {
      for (const cond of where.split(/\s+AND\s+/)) {
        const m = cond.match(/(?:[a-zA-Z_]+\.)?(\w+)\s*(=|LIKE)\s*\?/);
        if (!m) continue;
        const [, col, op] = m;
        const val = binds[bindIdx++];
        if (op === 'LIKE') {
          const needle = String(val).replace(/^%|%$/g, '');
          rows = rows.filter((r) => String(r[col] ?? '').includes(needle));
        } else {
          rows = rows.filter((r) => String(r[col]) === String(val));
        }
      }
    }
  }

  const orderMatch = sql.match(/ORDER BY\s+(.+?)(?:\s+LIMIT|$)/s);
  if (orderMatch) {
    for (const part of orderMatch[1].split(',').map((p) => p.trim()).reverse()) {
      const m = part.match(/(?:[a-zA-Z_]+\.)?(\w+)\s+(ASC|DESC)/i) ?? part.match(/(?:[a-zA-Z_]+\.)?(\w+)/);
      const col = m[1];
      const dir = (m[2] ?? 'ASC').toUpperCase() === 'DESC' ? -1 : 1;
      rows = [...rows].sort((a, b) => {
        const va = a[col];
        const vb = b[col];
        if (va == null) return 1;
        if (vb == null) return -1;
        const cmp = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb), 'ko');
        return cmp * dir;
      });
    }
  }

  const limitMatch = sql.match(/LIMIT\s+(\d+|\?)\s*(?:OFFSET\s+(\d+|\?))?/i);
  if (limitMatch) {
    const lim = limitMatch[1] === '?' ? Number(binds[bindIdx++]) : Number(limitMatch[1]);
    const off = limitMatch[2] ? (limitMatch[2] === '?' ? Number(binds[bindIdx++]) : Number(limitMatch[2])) : 0;
    rows = rows.slice(off, off + lim);
  }

  return rows.map((r) => ({ ...r }));
}

function mockD1(tables = TABLES) {
  const prepare = (sql) => {
    const state = { binds: [] };
    const api = {
      bind(...args) {
        state.binds = args;
        return api;
      },
      async first() {
        const rows = execSelect(sql, state.binds, tables);
        return rows[0] ?? null;
      },
      async all() {
        const results = execSelect(sql, state.binds, tables);
        return { results };
      },
      async run() {
        return { success: true, meta: {} };
      },
    };
    return api;
  };
  return {
    prepare,
    async exec() {
      return { success: true };
    },
    async batch(stmts) {
      return stmts.map(() => ({ success: true }));
    },
  };
}

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------
let passed = 0;
const failures = [];

async function test(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`  ok   ${name}`);
  } catch (err) {
    failures.push(name);
    console.error(`  FAIL ${name}`);
    console.error(`       ${err.message}`);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg ?? 'assertion failed');
}
function assertJson(res, status, msg) {
  assert(res.status === status, `${msg}: expected status ${status}, got ${res.status}`);
  const ct = res.headers.get('content-type') ?? '';
  assert(ct.includes('application/json'), `${msg}: expected application/json, got "${ct}"`);
  return res.json();
}
function assertEnvelope(body, msg) {
  assert(typeof body.count === 'number', `${msg}: count is not a number`);
  assert(Array.isArray(body.results), `${msg}: results is not an array`);
  assert(body.count === body.results.length, `${msg}: count (${body.count}) !== results.length (${body.results.length})`);
}

const baseEnv = {
  ASSETS: undefined,
  GOOGLE_SERVICE_ACCOUNT_KEY: '{}',
  GOOGLE_DRIVE_FOLDER_ID: '',
  GOOGLE_DRIVE_DATA_FOLDER_ID: '',
};

function get(path, db = mockD1(), extraEnv = {}) {
  return worker.fetch(new Request(`http://localhost${path}`), { ...baseEnv, DB: db, ...extraEnv }, { waitUntil() {} });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
console.log('[api-test] contract tests');

await test('GET /api/health -> { status: "ok" }', async () => {
  const body = await assertJson(await get('/api/health'), 200, 'health');
  assert(body.status === 'ok', `health: status is ${JSON.stringify(body.status)}`);
});

await test('GET /api/regions -> { count, results }', async () => {
  const body = await assertJson(await get('/api/regions'), 200, 'regions');
  assertEnvelope(body, 'regions');
  assert(body.count === 2, `regions: expected 2 fixture rows, got ${body.count}`);
  assert(typeof body.results[0].region === 'string', 'regions: result row missing region');
  assert('overrides' in body.results[0], 'regions: result row missing overrides field');
});

await test('GET /api/regions/:region -> detail', async () => {
  const region = encodeURIComponent('서울 강남구');
  const body = await assertJson(await get(`/api/regions/${region}`), 200, 'region detail');
  assert(body.score?.region === '서울 강남구', 'region detail: score.region mismatch');
  assert(Array.isArray(body.monthly_stats) && Array.isArray(body.cheongyak) && Array.isArray(body.development), 'region detail: sub-arrays missing');
});

await test('GET /api/regions/:unknown -> 404 JSON', async () => {
  const body = await assertJson(await get('/api/regions/%EC%97%86%EB%8A%94%EC%A7%80%EC%97%AD'), 404, 'region 404');
  assert(typeof body.error === 'string', 'region 404: error message missing');
});

await test('GET /api/cheongyak -> { count, limit, offset, results }', async () => {
  const body = await assertJson(await get('/api/cheongyak'), 200, 'cheongyak');
  assertEnvelope(body, 'cheongyak');
  assert(body.limit === 50 && body.offset === 0, `cheongyak: default limit/offset, got ${body.limit}/${body.offset}`);
  assert(body.count === 2, `cheongyak: expected 2 fixture rows, got ${body.count}`);
});

await test('GET /api/cheongyak?limit=1&offset=1 -> pagination', async () => {
  const body = await assertJson(await get('/api/cheongyak?limit=1&offset=1'), 200, 'cheongyak pagination');
  assert(body.limit === 1 && body.offset === 1, 'cheongyak pagination: echo mismatch');
  assert(body.results.length === 1, `cheongyak pagination: expected 1 row, got ${body.results.length}`);
});

await test('GET /api/cheongyak?limit=abc -> 400 JSON', async () => {
  const body = await assertJson(await get('/api/cheongyak?limit=abc'), 400, 'cheongyak bad limit');
  assert(typeof body.error === 'string', 'cheongyak bad limit: error missing');
});

await test('GET /api/cheongyak/search (no q) -> 400 JSON', async () => {
  const body = await assertJson(await get('/api/cheongyak/search'), 400, 'cheongyak search no q');
  assert(typeof body.error === 'string', 'cheongyak search no q: error missing');
});

await test('GET /api/development -> { count, results }', async () => {
  const body = await assertJson(await get('/api/development'), 200, 'development');
  assertEnvelope(body, 'development');
  assert(body.count === 1, `development: expected 1 fixture row, got ${body.count}`);
});

await test('GET /api/development?region=... -> filtered', async () => {
  const body = await assertJson(await get(`/api/development?region=${encodeURIComponent('서울 강남구')}`), 200, 'development filter');
  assertEnvelope(body, 'development filter');
  assert(body.results.every((r) => r.region === '서울 강남구'), 'development filter: row with wrong region');
});

await test('GET /api/evaluation -> { count, results }', async () => {
  const body = await assertJson(await get('/api/evaluation'), 200, 'evaluation');
  assertEnvelope(body, 'evaluation');
  assert(body.count === 1, `evaluation: expected 1 fixture row, got ${body.count}`);
});

await test('GET /api/evaluation/weights -> { count, results }', async () => {
  const body = await assertJson(await get('/api/evaluation/weights'), 200, 'evaluation weights');
  assertEnvelope(body, 'evaluation weights');
  assert(body.count === 0, `evaluation weights: expected 0 fixture rows, got ${body.count}`);
});

await test('GET /api/search?q=... -> { query, count, results }', async () => {
  const body = await assertJson(await get(`/api/search?q=${encodeURIComponent('강남')}`), 200, 'search');
  assert(body.query === '강남', `search: query echo mismatch: ${body.query}`);
  assertEnvelope(body, 'search');
  assert(body.count >= 1, `search: expected >= 1 match, got ${body.count}`);
});

await test('GET /api/search (no q) -> 400 JSON', async () => {
  const body = await assertJson(await get('/api/search'), 400, 'search no q');
  assert(body.error === 'missing required query param `q`', `search no q: unexpected error ${JSON.stringify(body)}`);
});

await test('onError: handler crash -> 500 { error: "internal_error" }', async () => {
  const boomDb = {
    prepare() {
      throw new Error('boom');
    },
    exec() {
      throw new Error('boom');
    },
    batch() {
      throw new Error('boom');
    },
  };
  const origErr = console.error;
  console.error = () => {}; // silence the expected error log
  try {
    const body = await assertJson(await get('/api/regions', boomDb), 500, 'onError');
    assert(body.error === 'internal_error', `onError: unexpected body ${JSON.stringify(body)}`);
  } finally {
    console.error = origErr;
  }
});

await test('unknown /api path -> 404 (not a crash)', async () => {
  const res = await get('/api/nope');
  assert(res.status === 404, `unknown path: expected 404, got ${res.status}`);
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
console.log('');
if (failures.length === 0) {
  console.log(`[api-test] all ${passed} tests passed`);
  process.exit(0);
} else {
  console.error(`[api-test] ${failures.length} of ${passed + failures.length} tests FAILED:`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
