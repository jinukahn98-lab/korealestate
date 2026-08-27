export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const type = response.headers.get('content-type') || '';
    if (!type.includes('text/html')) return response;

    const html = await response.text();
    const injected = html.includes('/deep-dive.js')
      ? html
      : html.replace('</body>', '<script src="/deep-dive.js?v=20260827-3" defer></script></body>');

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
