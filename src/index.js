export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/api/sync') {
      return handleSync(request, env);
    }

    return env.ASSETS.fetch(request);
  }
};

async function handleSync(request, env) {
  const token = request.headers.get('X-Sync-Token');
  if (!token || token.length !== 64) {
    return jsonResponse({ error: 'Invalid token' }, 401);
  }

  if (request.method === 'GET') {
    const value = await env.SYNC_KV.get(token);
    if (!value) return jsonResponse({ exists: false });
    return new Response(value, {
      headers: { 'Content-Type': 'application/json' }
    });
  }

  if (request.method === 'PUT') {
    const body = await request.text();
    try {
      JSON.parse(body);
    } catch (e) {
      return jsonResponse({ error: 'Invalid JSON' }, 400);
    }
    await env.SYNC_KV.put(token, body, { expirationTtl: 30 * 24 * 3600 });
    return jsonResponse({ success: true });
  }

  return new Response('Method not allowed', { status: 405 });
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}
