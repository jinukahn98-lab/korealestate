import { Hono } from 'hono';
import { cors } from 'hono/cors';
import regions from './routes/regions';
import cheongyak from './routes/cheongyak';
import development from './routes/development';
import evaluation from './routes/evaluation';
import search from './routes/search';
import { runDriveSync, runTableDataSync } from './lib/drive-sync';

interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  GOOGLE_SERVICE_ACCOUNT_KEY: string;
  GOOGLE_DRIVE_FOLDER_ID: string;
  GOOGLE_DRIVE_DATA_FOLDER_ID: string;
}

const app = new Hono<{ Bindings: Env }>();

// CORS for all routes
app.use('*', cors());

// API routes
app.route('/api/regions', regions);
app.route('/api/cheongyak', cheongyak);
app.route('/api/development', development);
app.route('/api/evaluation', evaluation);
app.route('/api/search', search);

// Health check
app.get('/api/health', (c) =>
  c.json({ status: 'ok', timestamp: new Date().toISOString() })
);

// Serve static files from public/ (via ASSETS binding) with SPA fallback
app.get('*', async (c) => {
  const url = new URL(c.req.url);
  // Try to serve the exact asset first
  if (c.env.ASSETS) {
    const response = await c.env.ASSETS.fetch(c.req.raw);
    if (response.status !== 404) return response;
  }
  // Fallback to index.html for SPA client-side routing
  if (c.env.ASSETS) {
    const indexResponse = await c.env.ASSETS.fetch(
      new Request(new URL('/index.html', url.toString()))
    );
    if (indexResponse.status !== 404) return indexResponse;
  }
  return c.text('Not found', 404);
});

export default {
  fetch: app.fetch,
  async scheduled(_event: ScheduledController, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(
      runDriveSync(env)
        .then((summary) => console.log('drive-sync:overrides', JSON.stringify(summary)))
        .catch((err) => console.error('drive-sync:overrides failed', err))
    );
    ctx.waitUntil(
      runTableDataSync(env)
        .then((summary) => console.log('drive-sync:data', JSON.stringify(summary)))
        .catch((err) => console.error('drive-sync:data failed', err))
    );
  }
} satisfies ExportedHandler<Env>;
