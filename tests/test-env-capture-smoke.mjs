import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';

const base = 'https://test.buyali.xyz';
const token = randomBytes(32).toString('hex');
const accountId = 'smoke-account';
const characterId = 'smoke-character';
const cloud = {
  exists: true,
  lastModified: new Date().toISOString(),
  data: {
    _lastModified: new Date().toISOString(),
    accounts: [{
      id: accountId, name: '自动验收账号', membership: 'none', characters: [{
        id: characterId, name: '自动验收角色', whiteEnergy: 1, whiteTimestamp: null,
        blueEnergy: 0, kina: 1, combatPower: 999, combatPowerUnit: 'K', itemLevel: 1
      }]
    }]
  }
};

let response = await fetch(base + '/api/sync', {
  method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Sync-Token': token },
  body: JSON.stringify(cloud)
});
assert.equal(response.status, 200, '测试数据应能写入测试 KV');

response = await fetch(base + '/api/capture/pair', {
  method: 'POST', headers: { 'X-Sync-Token': token }
});
assert.equal(response.status, 200, '测试环境应能创建配对码');
const { code } = await response.json();

response = await fetch(base + '/api/capture/redeem', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ code, deviceName: '自动验收' })
});
assert.equal(response.status, 200, '测试环境应能兑换设备令牌');
const { deviceToken } = await response.json();

const waiting = fetch(base + '/api/capture/events?after=0', {
  headers: { 'X-Sync-Token': token }
});
const started = performance.now();
response = await fetch(base + '/api/capture/apply', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + deviceToken },
  body: JSON.stringify({ accountId, characterId, fields: { kina: 782806341, combatPower: 1.023, combatPowerUnit: 'M' } })
});
assert.equal(response.status, 200, '测试采集数据应写入成功');
const eventResponse = await waiting;
const elapsed = performance.now() - started;
const eventResult = await eventResponse.json();
assert.equal(eventResult.events.length, 1, '等待中的网页请求应立即收到采集事件');
assert.equal(eventResult.events[0].data.accounts[0].characters[0].kina, 782806341);
assert.equal(eventResult.events[0].data.accounts[0].characters[0].combatPower, 1.023);
assert.equal(eventResult.events[0].data.accounts[0].characters[0].combatPowerUnit, 'M');
assert.ok(elapsed < 3000, `采集事件通知耗时应小于 3 秒，实际 ${Math.round(elapsed)}ms`);

response = await fetch(base + '/api/capture/state', { headers: { Authorization: 'Bearer ' + deviceToken } });
let state = await response.json();
assert.equal(state.accounts[0].characters[0].combatPowerUnit, 'M', '线上状态接口应保留 M 单位');

const applied = eventResult.events[0];
response = await fetch(base + '/api/capture/undo', {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + deviceToken },
  body: JSON.stringify({ transactionId: applied.transactionId })
});
assert.equal(response.status, 200, '线上 K/M 采集事务应可撤回');

response = await fetch(base + '/api/capture/apply', {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + deviceToken },
  body: JSON.stringify({ accountId, characterId, fields: { combatPower: 1023 } })
});
assert.equal(response.status, 200, '旧客户端纯数字 K 写入应保持兼容');
response = await fetch(base + '/api/capture/state', { headers: { Authorization: 'Bearer ' + deviceToken } });
state = await response.json();
assert.equal(state.accounts[0].characters[0].combatPower, 1023);
assert.equal(state.accounts[0].characters[0].combatPowerUnit, 'K');

console.log(`test environment capture event received in ${Math.round(elapsed)}ms`);
