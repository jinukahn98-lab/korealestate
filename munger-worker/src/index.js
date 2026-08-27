async function buildHtml(request, env) {
  const response = await env.ASSETS.fetch(request);
  const type = response.headers.get('content-type') || '';
  if (!type.includes('text/html')) return { response, html: null, injected: null };

  const html = await response.text();
  const injected = html.includes('/deep-dive.js')
    ? html
    : html.replace('</body>', '<script src="/deep-dive.js?v=20260827-4" defer></script></body>');
  return { response, html, injected };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/__munger_health') {
      const rootUrl = new URL('/', url);
      const rootRequest = new Request(rootUrl.toString(), { method: 'GET', headers: request.headers });
      const { response, html, injected } = await buildHtml(rootRequest, env);
      const jsResponse = await env.ASSETS.fetch(new Request(new URL('/deep-dive.js', url).toString()));
      return Response.json({
        ok: response.status === 200 && !!html && !!injected && jsResponse.status === 200,
        baseHtml: response.status === 200 && !!html,
        injected: !!injected && injected.includes('/deep-dive.js'),
        deepDiveAsset: jsResponse.status === 200,
        version: '20260827-4'
      }, { headers: { 'cache-control': 'no-store' } });
    }

    const { response, injected } = await buildHtml(request, env);
    if (injected == null) return response;

    const headers = new Headers(response.headers);
    headers.delete('content-length');
    headers.set('cache-control', 'no-cache');
    return new Response(injected, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
