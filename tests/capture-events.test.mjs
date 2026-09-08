import assert from 'node:assert/strict';
import { CaptureEventHub } from '../src/index.js';

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
