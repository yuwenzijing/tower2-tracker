export async function onRequestGet(context) {
  const token = context.request.headers.get('X-Sync-Token');
  if (!token || token.length !== 64) {
    return jsonResponse({ error: 'Invalid token' }, 401);
  }

  const value = await context.env.SYNC_KV.get(token);
  if (!value) {
    return jsonResponse({ exists: false });
  }

  return new Response(value, {
    headers: { 'Content-Type': 'application/json' }
  });
}

export async function onRequestPut(context) {
  const token = context.request.headers.get('X-Sync-Token');
  if (!token || token.length !== 64) {
    return jsonResponse({ error: 'Invalid token' }, 401);
  }

  const body = await context.request.text();
  try {
    JSON.parse(body);
  } catch (e) {
    return jsonResponse({ error: 'Invalid JSON' }, 400);
  }

  await context.env.SYNC_KV.put(token, body);
  return jsonResponse({ success: true });
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}
