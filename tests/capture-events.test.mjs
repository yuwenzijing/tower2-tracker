import assert from 'node:assert/strict';
import worker, { CaptureEventHub } from '../src/index.js';

class MemoryStorage {
  constructor() { this.values = new Map(); }
  async get(key) { return this.values.get(key); }
  async put(key, value) { this.values.set(key, structuredClone(value)); }
}

const hub = new CaptureEventHub({ storage: new MemoryStorage() });
const after = 0;
const waiting = hub.fetch(new Request(`https://events.test/?after=${after}&wait=1000`));
await new Promise(resolve => setTimeout(resolve, 10));
const createdResponse = await hub.fetch(new Request('https://events.test/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ type: 'applied', data: { value: 42 } })
}));
const created = await createdResponse.json();
assert.ok(created.id > after, '事件 ID 必须晚于客户端基线');

const response = await waiting;
const result = await response.json();
assert.equal(result.events.length, 1, '等待中的网页请求应在写入后立即收到事件');
assert.equal(result.events[0].data.value, 42);

console.log('capture event long-poll scenarios passed');

class MemoryKV {
  constructor() { this.values = new Map(); }
  async get(key, type) {
    const value = this.values.get(key);
    if (value == null) return null;
    return type === 'json' ? JSON.parse(value) : value;
  }
  async put(key, value) { this.values.set(key, value); }
  async delete(key) { this.values.delete(key); }
}

const kv = new MemoryKV();
const failedHub = {
  idFromName(value) { return value; },
  get() { return { async fetch() { throw new Error('Durable Object unavailable'); } }; }
};
const fallbackEnv = { SYNC_KV: kv, CAPTURE_EVENTS: failedHub };
const token = 'b'.repeat(64);
const accountId = 'fallback-account';
const characterId = 'fallback-character';
let fallbackResponse = await worker.fetch(new Request('https://example.test/api/sync', {
  method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Sync-Token': token },
  body: JSON.stringify({
    lastModified: 'initial', data: { accounts: [{ id: accountId, characters: [{
      id: characterId, name: 'fallback', whiteEnergy: 1, blueEnergy: 0, kina: 1, combatPower: 1, itemLevel: 1
    }] }] }
  })
}), fallbackEnv);
assert.equal(fallbackResponse.status, 200);
fallbackResponse = await worker.fetch(new Request('https://example.test/api/capture/pair', {
  method: 'POST', headers: { 'X-Sync-Token': token }
}), fallbackEnv);
const { code } = await fallbackResponse.json();
fallbackResponse = await worker.fetch(new Request('https://example.test/api/capture/redeem', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code })
}), fallbackEnv);
const { deviceToken } = await fallbackResponse.json();
fallbackResponse = await worker.fetch(new Request('https://example.test/api/capture/apply', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + deviceToken },
  body: JSON.stringify({ accountId, characterId, fields: { kina: 2 } })
}), fallbackEnv);
assert.equal(fallbackResponse.status, 200, '通知 Durable Object 出错时采集写入仍必须成功');
fallbackResponse = await worker.fetch(new Request('https://example.test/api/capture/events?after=0', {
  headers: { 'X-Sync-Token': token }
}), fallbackEnv);
const fallbackEvents = await fallbackResponse.json();
assert.equal(fallbackEvents.events.length, 1, '通知 Durable Object 出错时必须从 KV 回退读取事件');

console.log('capture event fallback scenarios passed');
