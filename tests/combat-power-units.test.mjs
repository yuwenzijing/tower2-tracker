import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const source = await fs.readFile(new URL('../src/index.js', import.meta.url), 'utf8');
const worker = (await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)).default;
const webSource = await fs.readFile(new URL('../public/index.html', import.meta.url), 'utf8');
assert.match(webSource, /\.stat-group \.combat-unit-select \{ display: none !important; \}/, 'unit selector is hidden when not editing');
assert.match(webSource, /\.stat-group\.editing \.combat-unit-select \{ display: inline-block !important; \}/, 'unit selector appears in edit mode');
assert.match(webSource, /class="stat-suffix combat-unit-label">\$\{ch\.combatPowerUnit\|\|'K'\}<\/span>/, 'idle state renders a plain unit label');

function extractFunction(name) {
  const start = webSource.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} exists in the webpage source`);
  const open = webSource.indexOf('{', start);
  let depth = 0;
  for (let index = open; index < webSource.length; index++) {
    if (webSource[index] === '{') depth++;
    if (webSource[index] === '}' && --depth === 0) return webSource.slice(start, index + 1);
  }
  throw new Error(`Unclosed function: ${name}`);
}

const character = { combatPower: 1023, combatPowerUnit: 'K' };
const webpagePower = new Function('findChar', 'pushUndo', 'saveData', 'render',
  `${extractFunction('setCombatPower')};${extractFunction('changeCombatPowerUnit')};return {setCombatPower,changeCombatPowerUnit};`
)(() => ({ ch: character }), () => {}, () => {}, () => {});
webpagePower.changeCombatPowerUnit('account', 'character', 'M');
assert.equal(character.combatPower, 1.023, 'web unit toggle should preserve represented power');
assert.equal(character.combatPowerUnit, 'M');
webpagePower.setCombatPower('account', 'character', '1.0234', 'M');
assert.equal(character.combatPower, 1.023, 'web M input should retain three decimals');

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

const env = { SYNC_KV: new MemoryKV() };
const syncToken = 'b'.repeat(64);
const accountId = 'account';
const characterId = 'character';
const data = { accounts: [{ id: accountId, characters: [
  { id: characterId, name: 'M角色', combatPower: 999, combatPowerUnit: 'K' },
  { id: 'legacy', name: '旧数据', combatPower: 850 }
] }] };

let response = await worker.fetch(new Request('https://example.test/api/sync', {
  method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Sync-Token': syncToken },
  body: JSON.stringify({ exists: true, lastModified: 'r1', data })
}), env);
assert.equal(response.status, 200);

response = await worker.fetch(new Request('https://example.test/api/capture/pair', {
  method: 'POST', headers: { 'X-Sync-Token': syncToken }
}), env);
const { code } = await response.json();
response = await worker.fetch(new Request('https://example.test/api/capture/redeem', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ code, deviceName: 'combat-unit-test' })
}), env);
const { deviceToken } = await response.json();

response = await worker.fetch(new Request('https://example.test/api/capture/apply', {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${deviceToken}` },
  body: JSON.stringify({ accountId, characterId, fields: { combatPower: 1.0234, combatPowerUnit: 'M' } })
}), env);
assert.equal(response.status, 200, 'M 战斗力应可由采集接口写入');
const { transactionId } = await response.json();

response = await worker.fetch(new Request('https://example.test/api/capture/state', {
  headers: { Authorization: `Bearer ${deviceToken}` }
}), env);
const state = await response.json();
assert.equal(state.accounts[0].characters[0].combatPower, 1.023, 'M 保留三位小数');
assert.equal(state.accounts[0].characters[0].combatPowerUnit, 'M', '采集写入应保留 M 单位');
assert.equal(state.accounts[0].characters[1].combatPowerUnit, 'K', '旧版纯数值按 K 返回');

response = await worker.fetch(new Request('https://example.test/api/capture/undo', {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${deviceToken}` },
  body: JSON.stringify({ transactionId })
}), env);
assert.equal(response.status, 200, 'K/M 数值和单位应能作为一次事务撤回');
response = await worker.fetch(new Request('https://example.test/api/capture/state', {
  headers: { Authorization: `Bearer ${deviceToken}` }
}), env);
const reverted = await response.json();
assert.equal(reverted.accounts[0].characters[0].combatPower, 999);
assert.equal(reverted.accounts[0].characters[0].combatPowerUnit, 'K');

response = await worker.fetch(new Request('https://example.test/api/capture/apply', {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${deviceToken}` },
  body: JSON.stringify({ accountId, characterId, fields: { combatPower: 1023 } })
}), env);
assert.equal(response.status, 200, '旧采集客户端仍可提交纯数字 K 战斗力');
response = await worker.fetch(new Request('https://example.test/api/capture/state', {
  headers: { Authorization: `Bearer ${deviceToken}` }
}), env);
const legacyClientState = await response.json();
assert.equal(legacyClientState.accounts[0].characters[0].combatPower, 1023);
assert.equal(legacyClientState.accounts[0].characters[0].combatPowerUnit, 'K');

console.log('combat power K/M unit scenarios passed');
