import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const source = await fs.readFile(new URL('../src/index.js', import.meta.url), 'utf8');
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const worker = (await import(moduleUrl)).default;

class MemoryKV {
  constructor() { this.values = new Map(); }
  async get(key, type) {
    const value = this.values.get(key);
    if (value == null) return null;
    return type === 'json' ? JSON.parse(value) : value;
  }
  async put(key, value) { this.values.set(key, value); }
}

const kv = new MemoryKV();
const env = { SYNC_KV: kv };
const token = 'a'.repeat(64);

async function put(payload) {
  return worker.fetch(new Request('https://example.test/api/sync', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Sync-Token': token },
    body: JSON.stringify(payload)
  }), env);
}

let response = await put({ data: { value: 1 }, lastModified: 'rev-1', exists: true });
assert.equal(response.status, 200, '首次写入应成功');

response = await put({
  data: { value: 2 }, lastModified: 'rev-2', exists: true,
  baseLastModified: 'rev-1'
});
assert.equal(response.status, 200, '基于当前版本的写入应成功');

response = await put({
  data: { value: 3 }, lastModified: 'rev-3', exists: true,
  baseLastModified: 'rev-1'
});
assert.equal(response.status, 409, '基于旧版本的写入必须被拒绝');
assert.equal((await response.json()).error, 'SYNC_CONFLICT');

response = await worker.fetch(new Request('https://example.test/api/sync', {
  headers: { 'X-Sync-Token': token }
}), env);
const cloud = await response.json();
assert.equal(cloud.lastModified, 'rev-2', '冲突写入不能覆盖较新的云端版本');
assert.equal(cloud.data.value, 2);

console.log('sync CAS scenarios passed');
