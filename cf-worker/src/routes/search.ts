import { Hono } from 'hono';

const app = new Hono<{ Bindings: { DB: D1Database } }>();

// GET /api/search?q= — FTS5 full-text search over wiki_fts
// Returns title, category, date_token, and a content snippet with highlights.
app.get('/', async (c) => {
  const q = c.req.query('q')?.trim() ?? '';
  if (!q) {
    return c.json({ error: 'missing required query param `q`' }, 400);
  }

  // wiki_fts column order: 0=title, 1=category, 2=content, 3=date_token
  // snippet() builds a highlighted excerpt from the content column (index 2).
  const { results } = await c.env.DB.prepare(
    `SELECT title,
            category,
            date_token,
            snippet(wiki_fts, 2, '<mark>', '</mark>', '…', 24) AS snippet
     FROM wiki_fts
     WHERE wiki_fts MATCH ?
     ORDER BY rank
     LIMIT 20`
  )
    .bind(q)
    .all();

  return c.json({ query: q, count: results.length, results });
});

export default app;
