import { Hono } from 'hono';

const app = new Hono<{ Bindings: { DB: D1Database } }>();

// GET /api/evaluation — recent daily_eval_log entries (last 30)
app.get('/', async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT id, run_date, task, status, result_json, created_at
     FROM daily_eval_log
     ORDER BY id DESC
     LIMIT 30`
  ).all();
  return c.json({ count: results.length, results });
});

// GET /api/evaluation/weights — ML factor weights, optimized weight DESC
app.get('/weights', async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT factor_name, default_weight, optimized_weight, updated_at
     FROM ml_weights
     ORDER BY optimized_weight DESC`
  ).all();
  return c.json({ count: results.length, results });
});

// GET /api/evaluation/:id — single eval log by id
app.get('/:id', async (c) => {
  const id = Number(c.req.param('id'));
  if (!Number.isFinite(id) || id <= 0) {
    return c.json({ error: 'id must be a positive integer' }, 400);
  }

  const row = await c.env.DB.prepare(
    `SELECT id, run_date, task, status, result_json, created_at
     FROM daily_eval_log
     WHERE id = ?`
  )
    .bind(id)
    .first();

  if (!row) {
    return c.json({ error: 'eval log not found', id }, 404);
  }

  return c.json(row);
});

export default app;
