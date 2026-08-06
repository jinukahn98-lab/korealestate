import { Hono } from 'hono';
import { loadOverrides } from '../lib/drive-sync';

const app = new Hono<{ Bindings: { DB: D1Database } }>();

// GET /api/regions — all regions, ranked by total_score DESC
app.get('/', async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT region, total_score, grade, factors, version, scored_at
     FROM scorer_results
     ORDER BY total_score DESC`
  ).all<{ region: string; [key: string]: unknown }>();

  const overrides = await loadOverrides(c.env.DB, results.map((r) => r.region));
  const withOverrides = results.map((row) => ({ ...row, overrides: overrides.get(row.region) ?? {} }));

  return c.json({ count: withOverrides.length, results: withOverrides });
});

// GET /api/regions/:region — single region detail
// Aggregates the score row + last 12 monthly_stats + 5 cheongyak + 5 development
app.get('/:region', async (c) => {
  const region = decodeURIComponent(c.req.param('region'));

  // Score row
  const score = await c.env.DB.prepare(
    `SELECT region, total_score, grade, factors, version, scored_at
     FROM scorer_results
     WHERE region = ?`
  )
    .bind(region)
    .first();

  if (!score) {
    return c.json({ error: 'region not found', region }, 404);
  }

  const overrides = await loadOverrides(c.env.DB, [region]);

  // Last 12 monthly stats
  const { results: monthly_stats } = await c.env.DB.prepare(
    `SELECT year_month, avg_price, trade_count, avg_jeonse_deposit, jeonse_rate
     FROM monthly_stats
     WHERE region = ?
     ORDER BY year_month DESC
     LIMIT 12`
  )
    .bind(region)
    .all();

  // Top 5 cheongyak (public housing lottery) for the region
  const { results: cheongyak } = await c.env.DB.prepare(
    `SELECT id, region, pblanc_name, total_supply, total_competition,
            score_cutoff, supply_price, market_price, pblanc_start, pblanc_end
     FROM external_cheongyak
     WHERE region = ?
     ORDER BY pblanc_start DESC
     LIMIT 5`
  )
    .bind(region)
    .all();

  // Top 5 development projects for the region
  const { results: development } = await c.env.DB.prepare(
    `SELECT id, region, project_name, project_type, status,
            expected_completion, impact_score
     FROM external_development
     WHERE region = ?
     ORDER BY impact_score DESC
     LIMIT 5`
  )
    .bind(region)
    .all();

  return c.json({
    score,
    overrides: overrides.get(region) ?? {},
    monthly_stats,
    cheongyak,
    development,
  });
});

// GET /api/regions/:region/chart — monthly stats formatted for charting
app.get('/:region/chart', async (c) => {
  const region = decodeURIComponent(c.req.param('region'));

  const { results } = await c.env.DB.prepare(
    `SELECT year_month, avg_price, trade_count, jeonse_rate
     FROM monthly_stats
     WHERE region = ?
     ORDER BY year_month ASC`
  )
    .bind(region)
    .all();

  return c.json({ region, count: results.length, results });
});

export default app;
