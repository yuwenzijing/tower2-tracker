import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const app = await fs.readFile(new URL('../public/app.js', import.meta.url), 'utf8');
const html = await fs.readFile(new URL('../public/index.html', import.meta.url), 'utf8');
const worker = await fs.readFile(new URL('../src/index.js', import.meta.url), 'utf8');
const headers = await fs.readFile(new URL('../public/_headers', import.meta.url), 'utf8');

assert.match(app,
  /\(!DATA\.accounts \|\| DATA\.accounts\.length === 0\)[\s\S]*?applyCloudSyncData\(cloud\.data, cloudMod\)/,
  '空浏览器应直接恢复已有云端数据');
assert.match(app, /setTimeout\(function\(\) \{ syncOnLoad\(\); \}, 0\)/,
  '主应用应独立启动云同步');
assert.match(app, /尚未设置同步口令，请点击“同步”恢复云端数据/,
  '空浏览器没有口令时应提供明确指引');
assert.match(html, /app\.js\?v=1\.3\.8\.2/,
  '修复后应提升资源查询版本，绕过旧浏览器缓存');
assert.match(worker, /url\.pathname\.endsWith\('\.html'\)[\s\S]*?Cache-Control', 'no-store'/,
  'Worker 不应缓存 HTML 外壳');
assert.match(headers, /\/index\.html\s+Cache-Control: no-store/,
  '静态资源规则不应缓存 HTML 外壳');

console.log('web sync startup recovery scenarios passed');
