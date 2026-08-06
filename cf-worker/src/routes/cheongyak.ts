import { Hono } from 'hono';

const app = new Hono<{ Bindings: { DB: D1Database } }>();

// GET /api/cheongyak — list public housing lotteries, paginated, with score join
// Query params: limit (default 50, max 200), offset (default 0)
app.get('/', async (c) => {
  const limitRaw = c.req.query('limit');
  const offsetRaw = c.req.query('offset');
  const limit = limitRaw === undefined ? 50 : Number(limitRaw);
  const offset = offsetRaw === undefined ? 0 : Number(offsetRaw);
  if (!Number.isInteger(limit) || !Number.isInteger(offset)) {
    return c.json({ error: 'invalid `limit`/`offset`: must be integers' }, 400);
  }
  const clampedLimit = Math.min(Math.max(limit, 0), 200);
  const clampedOffset = Math.max(offset, 0);

  const { results } = await c.env.DB.prepare(
    `SELECT c.id, c.region, c.pblanc_name, c.total_supply, c.total_competition,
            c.score_cutoff, c.supply_price, c.market_price, c.pblanc_start,
            c.pblanc_end, s.total_score, s.grade
     FROM external_cheongyak c
     LEFT JOIN scorer_results s ON s.region = c.region
     ORDER BY c.pblanc_start DESC
     LIMIT ? OFFSET ?`
  )
    .bind(clampedLimit, clampedOffset)
    .all();

  return c.json({ count: results.length, limit, offset, results });
});

// GET /api/cheongyak/search?q= — LIKE search on pblanc_name
app.get('/search', async (c) => {
  const q = c.req.query('q')?.trim() ?? '';
  if (!q) {
    return c.json({ error: 'missing required query param `q`' }, 400);
  }

  const { results } = await c.env.DB.prepare(
    `SELECT c.id, c.region, c.pblanc_name, c.total_supply, c.total_competition,
            c.score_cutoff, c.supply_price, c.market_price, c.pblanc_start,
            c.pblanc_end, s.total_score, s.grade
     FROM external_cheongyak c
     LEFT JOIN scorer_results s ON s.region = c.region
     WHERE c.pblanc_name LIKE ?
     ORDER BY c.pblanc_start DESC
     LIMIT 50`
  )
    .bind(`%${q}%`)
    .all();

  return c.json({ query: q, count: results.length, results });
});

export default app;
