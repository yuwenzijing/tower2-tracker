export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/api/sync') {
      return handleSync(request, env);
    }

    if (url.pathname === '/api/ocr' && request.method === 'POST') {
      return handleOcr(request, env);
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

async function handleOcr(request, env) {
  const apiKey = env.BAIDU_OCR_API_KEY;
  const secretKey = env.BAIDU_OCR_SECRET_KEY;
  if (!apiKey || !secretKey) {
    return jsonResponse({ error: 'OCR 服务未配置' }, 503);
  }

  let body;
  try {
    body = await request.json();
  } catch (e) {
    return jsonResponse({ error: 'Invalid JSON' }, 400);
  }
  const imageBase64 = body.image;
  if (!imageBase64 || typeof imageBase64 !== 'string') {
    return jsonResponse({ error: 'Missing image' }, 400);
  }

  const token = await getBaiduToken(env, apiKey, secretKey);
  if (!token) {
    return jsonResponse({ error: '百度 OCR token 获取失败' }, 502);
  }

  const ocrUrl = `https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token=${token}`;
  const payload = 'image=' + encodeURIComponent(imageBase64);
  if (payload.length > 4 * 1024 * 1024) {
    return jsonResponse({ error: '图片过大，请缩小窗口后重试', size: payload.length }, 413);
  }
  const ocrRes = await fetch(ocrUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: payload
  });
  const ocrData = await ocrRes.json();

  if (ocrData.error_code) {
    return jsonResponse({ error: ocrData.error_msg || 'OCR failed', code: ocrData.error_code }, 502);
  }

  const words = (ocrData.words_result || []).map(w => w.words);
  return jsonResponse({ words, text: words.join(' '), count: words.length });
}

async function getBaiduToken(env, apiKey, secretKey) {
  const cacheKey = '_baidu_ocr_token';
  const cached = await env.SYNC_KV.get(cacheKey);
  if (cached) return cached;

  const tokenUrl = `https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id=${apiKey}&client_secret=${secretKey}`;
  const res = await fetch(tokenUrl, { method: 'POST' });
  const data = await res.json();
  if (!data.access_token) return null;

  await env.SYNC_KV.put(cacheKey, data.access_token, { expirationTtl: data.expires_in || 2592000 });
  return data.access_token;
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}
