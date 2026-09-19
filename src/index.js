const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };
const SYNC_TTL = 30 * 24 * 3600;
const PAIR_TTL = 5 * 60;
const DEVICE_TTL = 365 * 24 * 3600;
const TX_TTL = 15 * 60;
const UNDO_WINDOW_MS = 8000;
const ALLOWED_FIELDS = new Set(['whiteEnergy', 'blueEnergy', 'kina', 'combatPower', 'itemLevel']);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/api/sync') return handleSync(request, env);
    if (url.pathname.startsWith('/api/capture/')) return handleCapture(request, env, url);
    return env.ASSETS.fetch(request);
  }
};

export class CaptureEventHub {
  constructor(state) {
    // Keep the storage handle directly. This is the Durable Object pattern
    // supported by both the legacy class API and current Workers runtime.
    this.storage = state.storage;
    this.waiters = new Set();
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === 'POST') {
      const event = await request.json();
      const events = await this.storage.get('events') || [];
      const id = Math.max(Date.now(), events.length ? events[events.length - 1].id + 1 : 1);
      const stored = { ...event, id, createdAt: new Date().toISOString() };
      events.push(stored);
      await this.storage.put('events', events.slice(-20));
      for (const notify of this.waiters) notify();
      this.waiters.clear();
      return json(stored);
    }
    const after = Number(url.searchParams.get('after') || 0);
    let events = await this.storage.get('events') || [];
    let pending = events.filter(event => event.id > after);
    const wait = Math.min(25000, Math.max(0, Number(url.searchParams.get('wait') || 0)));
    if (!pending.length && wait) {
      await new Promise(resolve => {
        let timer;
        const notify = () => { clearTimeout(timer); this.waiters.delete(notify); resolve(); };
        timer = setTimeout(notify, wait);
        this.waiters.add(notify);
      });
      events = await this.storage.get('events') || [];
      pending = events.filter(event => event.id > after);
    }
    return json({ events: pending });
  }
}

// V2 uses a fresh Durable Object class/migration. The original event hub is
// retained for existing deployments, while new requests avoid any poisoned
// instance state from the previous class registration.
export class CaptureEventHubV2 extends CaptureEventHub {}

async function handleSync(request, env) {
  const token = validSyncToken(request.headers.get('X-Sync-Token'));
  if (!token) return json({ error: 'Invalid token' }, 401);
  if (request.method === 'GET') {
    const value = await env.SYNC_KV.get(token);
    return value ? new Response(value, { headers: JSON_HEADERS }) : json({ exists: false });
  }
  if (request.method === 'PUT') {
    const body = await request.text();
    let incoming;
    try { incoming = JSON.parse(body); } catch (_) { return json({ error: 'Invalid JSON' }, 400); }
    const current = await env.SYNC_KV.get(token, 'json');
    const baseLastModified = incoming && incoming.baseLastModified;
    if (baseLastModified && current && current.lastModified !== baseLastModified) {
      return json({
        error: 'SYNC_CONFLICT',
        cloudLastModified: current.lastModified || null
      }, 409);
    }
    if (incoming && typeof incoming === 'object') delete incoming.baseLastModified;
    await env.SYNC_KV.put(token, JSON.stringify(incoming), { expirationTtl: SYNC_TTL });
    return json({ success: true });
  }
  return json({ error: 'Method not allowed' }, 405);
}

async function handleCapture(request, env, url) {
  const route = url.pathname.slice('/api/capture/'.length);
  if (route === 'pair' && request.method === 'POST') return createPair(request, env);
  if (route === 'redeem' && request.method === 'POST') return redeemPair(request, env);
  if (route === 'events' && request.method === 'GET') return captureEvents(request, env, url);

  const device = await authenticateDevice(request, env);
  if (!device) return json({ error: 'Invalid device token' }, 401);
  if (route === 'state' && request.method === 'GET') return deviceState(env, device);
  if (route === 'apply' && request.method === 'POST') return applyCapture(request, env, device);
  if (route === 'undo' && request.method === 'POST') return undoCapture(request, env, device);
  if (route === 'create-character' && request.method === 'POST') return createCharacter(request, env, device);
  return json({ error: 'Not found' }, 404);
}

async function createPair(request, env) {
  const syncToken = validSyncToken(request.headers.get('X-Sync-Token'));
  if (!syncToken) return json({ error: '请先设置有效的云同步口令' }, 401);
  const cloud = await readCloud(env, syncToken);
  if (!cloud || !cloud.data) return json({ error: '请先把本地数据同步到云端' }, 409);
  let code;
  do { code = String(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000).padStart(6, '0'); }
  while (await env.SYNC_KV.get('capture:pair:' + code));
  await env.SYNC_KV.put('capture:pair:' + code, JSON.stringify({ syncToken, createdAt: Date.now() }), { expirationTtl: PAIR_TTL });
  return json({ code, expiresIn: PAIR_TTL });
}

async function redeemPair(request, env) {
  const body = await request.json().catch(() => null);
  const code = body && String(body.code || '').replace(/\D/g, '');
  if (!code || code.length !== 6) return json({ error: '配对码格式错误' }, 400);
  const key = 'capture:pair:' + code;
  const pair = await env.SYNC_KV.get(key, 'json');
  if (!pair) return json({ error: '配对码无效或已过期' }, 404);
  const deviceToken = randomHex(32);
  const device = {
    syncToken: pair.syncToken,
    name: String(body.deviceName || 'Windows 采集助手').slice(0, 80),
    createdAt: new Date().toISOString()
  };
  await Promise.all([
    env.SYNC_KV.put('capture:device:' + deviceToken, JSON.stringify(device), { expirationTtl: DEVICE_TTL }),
    env.SYNC_KV.delete(key)
  ]);
  return json({ deviceToken, deviceName: device.name });
}

async function captureEvents(request, env, url) {
  const syncToken = validSyncToken(request.headers.get('X-Sync-Token'));
  if (!syncToken) return json({ error: 'Invalid token' }, 401);
  const after = Number(url.searchParams.get('after') || 0);
  if (env.CAPTURE_EVENTS) {
    try {
      const stub = env.CAPTURE_EVENTS.get(env.CAPTURE_EVENTS.idFromName(syncToken));
      const response = await stub.fetch('https://capture-events.local/?after=' + after + '&wait=25000');
      if (response.ok) return response;
      console.error('Capture event hub read failed:', response.status);
    } catch (error) {
      console.error('Capture event hub read threw:', error && error.message ? error.message : error);
    }
  }
  return readFallbackEvents(env, syncToken, after, 25000);
}

async function deviceState(env, device) {
  const cloud = await readCloud(env, device.syncToken);
  if (!cloud || !cloud.data) return json({ error: '云端数据不存在' }, 404);
  const accounts = (cloud.data.accounts || []).map(account => ({
    id: account.id,
    name: account.name,
    membership: account.membership,
    characters: (account.characters || []).map(character => ({
      id: character.id,
      name: character.name,
      charClass: character.charClass || '',
      whiteEnergy: character.whiteEnergy || 0,
      whiteEnergyDisplay: effectiveWhiteEnergy(account, character),
      whiteTimestamp: character.whiteTimestamp || null,
      blueEnergy: character.blueEnergy || 0,
      kina: character.kina,
      combatPower: character.combatPower,
      itemLevel: character.itemLevel
    }))
  }));
  return json({ accounts, lastModified: cloud.lastModified });
}

function effectiveWhiteEnergy(account, character) {
  const baseline = Number(character.whiteEnergy) || 0;
  if (!character.whiteTimestamp || baseline >= 840) return Math.floor(Math.min(840, baseline));
  const from = Date.parse(character.whiteTimestamp);
  if (!Number.isFinite(from)) return Math.floor(Math.min(840, baseline));
  // Beijing recovery marks (02/05/08/.../23) are exactly UTC three-hour
  // boundaries. Excluding the starting boundary and including the current one
  // is therefore equivalent to the difference between these buckets.
  const interval = 3 * 60 * 60 * 1000;
  const marks = Math.max(0, Math.floor(Date.now() / interval) - Math.floor(from / interval));
  const step = account && account.membership === 'kuiling' ? 15 : 7.5;
  return Math.floor(Math.min(840, baseline + marks * step));
}

async function applyCapture(request, env, device) {
  const body = await request.json().catch(() => null);
  if (!body) return json({ error: 'Invalid JSON' }, 400);
  const fields = validateFields(body.fields);
  if (!fields.ok) return json({ error: fields.error }, 400);
  const cloud = await readCloud(env, device.syncToken);
  if (!cloud || !cloud.data) return json({ error: '云端数据不存在' }, 404);
  const target = findCharacter(cloud.data, body.accountId, body.characterId);
  if (!target) return json({ error: '目标角色不存在' }, 404);

  const before = {};
  const after = {};
  for (const [field, value] of Object.entries(fields.value)) {
    before[field] = target.character[field] ?? null;
    target.character[field] = value;
    after[field] = value;
  }
  if ('whiteEnergy' in fields.value) {
    before.whiteTimestamp = target.character.whiteTimestamp ?? null;
    target.character.whiteTimestamp = new Date().toISOString();
    after.whiteTimestamp = target.character.whiteTimestamp;
  }
  const transactionId = 'capture-' + Date.now().toString(36) + '-' + randomHex(4);
  const appliedModified = new Date().toISOString();
  cloud.data._lastModified = appliedModified;
  cloud.lastModified = appliedModified;
  const transaction = {
    transactionId,
    syncToken: device.syncToken,
    accountId: target.account.id,
    characterId: target.character.id,
    characterName: target.character.name,
    before,
    after,
    appliedModified,
    createdAt: Date.now(),
    status: 'applied'
  };
  await Promise.all([
    writeCloud(env, device.syncToken, cloud),
    env.SYNC_KV.put('capture:tx:' + transactionId, JSON.stringify(transaction), { expirationTtl: TX_TTL })
  ]);
  await appendEvent(env, device.syncToken, {
    type: 'applied', transactionId, characterName: target.character.name, data: cloud.data
  });
  return json({ success: true, transactionId, characterName: target.character.name, undoUntil: transaction.createdAt + UNDO_WINDOW_MS });
}

async function undoCapture(request, env, device) {
  const body = await request.json().catch(() => null);
  const transactionId = body && String(body.transactionId || '');
  const key = 'capture:tx:' + transactionId;
  const tx = await env.SYNC_KV.get(key, 'json');
  if (!tx || tx.syncToken !== device.syncToken) return json({ error: '事务不存在' }, 404);
  if (tx.status !== 'applied') return json({ error: '事务已经撤回' }, 409);
  if (Date.now() > tx.createdAt + UNDO_WINDOW_MS) return json({ error: '撤回时间已结束' }, 410);
  const cloud = await readCloud(env, device.syncToken);
  if (!cloud || cloud.lastModified !== tx.appliedModified) return json({ error: '采集后数据已发生其他修改' }, 409);
  const target = findCharacter(cloud.data, tx.accountId, tx.characterId);
  if (!target) return json({ error: '目标角色不存在' }, 404);
  for (const [field, value] of Object.entries(tx.before)) target.character[field] = value;
  const revertedModified = new Date().toISOString();
  cloud.data._lastModified = revertedModified;
  cloud.lastModified = revertedModified;
  tx.status = 'reverted';
  tx.revertedAt = Date.now();
  await Promise.all([
    writeCloud(env, device.syncToken, cloud),
    env.SYNC_KV.put(key, JSON.stringify(tx), { expirationTtl: TX_TTL })
  ]);
  await appendEvent(env, device.syncToken, {
    type: 'reverted', transactionId, characterName: target.character.name, data: cloud.data
  });
  return json({ success: true, transactionId });
}

async function createCharacter(request, env, device) {
  const body = await request.json().catch(() => null);
  const name = body && String(body.name || '').trim();
  if (!name || name.length > 40) return json({ error: '角色名无效' }, 400);
  const cloud = await readCloud(env, device.syncToken);
  const account = cloud && cloud.data && (cloud.data.accounts || []).find(item => item.id === body.accountId);
  if (!account) return json({ error: '目标账号不存在' }, 404);
  const character = {
    id: Date.now().toString(36) + randomHex(3), name, charClass: '', whiteEnergy: 0, whiteTimestamp: null,
    blueEnergy: 0, blueBackpackLarge: null, blueBackpackSmall: null, awakeningDone: null, abyssDone: null,
    sanctuary1Done: null, sanctuary2Done: null, sanctuary3Done: null, shopDone: null, transformDone: null,
    sanctuary1Name: null, sanctuary2Name: null, sanctuary3Name: null,
    trialDone: null, trialLv: 0, itemLevel: null, combatPower: null, kina: null
  };
  account.characters = account.characters || [];
  account.characters.push(character);
  cloud.data._lastModified = new Date().toISOString();
  cloud.lastModified = cloud.data._lastModified;
  await writeCloud(env, device.syncToken, cloud);
  return json({ success: true, accountId: account.id, character });
}

function validateFields(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return { ok: false, error: '没有可写入字段' };
  const result = {};
  for (const [key, raw] of Object.entries(input)) {
    if (!ALLOWED_FIELDS.has(key)) continue;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0) return { ok: false, error: key + ' 数值无效' };
    if (key === 'whiteEnergy' && value > 840) return { ok: false, error: '白奥德超出范围' };
    if (key === 'blueEnergy' && value > 2000) return { ok: false, error: '蓝奥德超出范围' };
    if (key === 'combatPower' && value > 999999999) return { ok: false, error: key + ' 超出范围' };
    if (key === 'itemLevel' && value > 9999) return { ok: false, error: key + ' 超出范围' };
    if (key === 'kina' && value > 999999999999) return { ok: false, error: '基纳超出范围' };
    result[key] = (key === 'combatPower') ? Math.round(value * 10) / 10 : Math.floor(value);
  }
  return Object.keys(result).length ? { ok: true, value: result } : { ok: false, error: '没有可写入字段' };
}

async function authenticateDevice(request, env) {
  const auth = request.headers.get('Authorization') || '';
  const match = auth.match(/^Bearer\s+([a-f0-9]{64})$/i);
  return match ? await env.SYNC_KV.get('capture:device:' + match[1], 'json') : null;
}

function validSyncToken(value) { return /^[a-f0-9]{64}$/i.test(value || '') ? value.toLowerCase() : null; }
function findCharacter(data, accountId, characterId) {
  const account = (data.accounts || []).find(item => item.id === accountId);
  const character = account && (account.characters || []).find(item => item.id === characterId);
  return character ? { account, character } : null;
}
async function readCloud(env, token) { return await env.SYNC_KV.get(token, 'json'); }
async function writeCloud(env, token, cloud) { await env.SYNC_KV.put(token, JSON.stringify(cloud), { expirationTtl: SYNC_TTL }); }
function eventKey(token) { return 'capture:events:' + token; }
async function appendEvent(env, token, event) {
  if (env.CAPTURE_EVENTS) {
    try {
      const stub = env.CAPTURE_EVENTS.get(env.CAPTURE_EVENTS.idFromName(token));
      const response = await stub.fetch('https://capture-events.local/', {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(event)
      });
      if (response.ok) return;
      console.error('Capture event hub write failed:', response.status);
    } catch (error) {
      // Cloud data has already been persisted. Never turn a successful capture
      // into a 500 merely because the notification channel is unavailable.
      console.error('Capture event hub write threw:', error && error.message ? error.message : error);
    }
  }
  await appendFallbackEvent(env, token, event);
}

async function readFallbackEvents(env, token, after, waitMs = 0) {
  const key = eventKey(token);
  const deadline = Date.now() + Math.max(0, waitMs);
  while (true) {
    const events = await env.SYNC_KV.get(key, 'json') || [];
    const pending = events.filter(event => event.id > after);
    if (pending.length || Date.now() >= deadline) return json({ events: pending });
    await new Promise(resolve => setTimeout(resolve, Math.min(250, deadline - Date.now())));
  }
}

async function appendFallbackEvent(env, token, event) {
  const key = eventKey(token);
  const events = await env.SYNC_KV.get(key, 'json') || [];
  const id = Math.max(Date.now(), events.length ? events[events.length - 1].id + 1 : 1);
  events.push({ ...event, id, createdAt: new Date().toISOString() });
  await env.SYNC_KV.put(key, JSON.stringify(events.slice(-20)), { expirationTtl: SYNC_TTL });
}
function randomHex(bytes) {
  const values = crypto.getRandomValues(new Uint8Array(bytes));
  return Array.from(values, value => value.toString(16).padStart(2, '0')).join('');
}
function json(data, status = 200) { return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS }); }
