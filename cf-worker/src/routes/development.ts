import { Hono } from 'hono';

const app = new Hono<{ Bindings: { DB: D1Database } }>();

// GET /api/development — all development projects, optional ?region= filter
app.get('/', async (c) => {
  const region = c.req.query('region')?.trim();

  if (region) {
    const decoded = decodeURIComponent(region);
    const { results } = await c.env.DB.prepare(
      `SELECT id, region, project_name, project_type, status,
              expected_completion, impact_score
       FROM external_development
       WHERE region = ?
       ORDER BY impact_score DESC, id ASC`
    )
      .bind(decoded)
      .all();
    return c.json({ region: decoded, count: results.length, results });
  }

  const { results } = await c.env.DB.prepare(
    `SELECT id, region, project_name, project_type, status,
            expected_completion, impact_score
     FROM external_development
     ORDER BY impact_score DESC, id ASC`
  ).all();

  return c.json({ count: results.length, results });
});

export default app;
