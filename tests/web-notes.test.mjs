import assert from 'node:assert/strict';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');

assert.match(source, /if \(ch\.note === undefined\) ch\.note = '';/, '旧数据应补齐备注字段');
assert.match(source, /note: '',/, '新角色应包含备注字段');
assert.match(source, /if \(isSelected\) \{[\s\S]*?noteHtml =/, '未选中角色不应渲染备注入口');
assert.match(source, /noteTextLength\(note\) > 20/, '长备注阈值应为 20 个字符');
assert.match(source, /event\.key === 'Enter'/, 'Enter 应保存');
assert.match(source, /event\.key === 'Escape'/, 'Esc 应取消');
assert.match(source, /document\.addEventListener\('pointerdown'/, '点击外部应保存');
assert.match(source, /r\.ch\.note = next;[\s\S]*?saveData\(\);/, '备注应进入现有保存及同步链路');
assert.match(source, /height: 31px;[\s\S]*?class="todo-subtitle"/, '备注行应保持固定高度');
assert.doesNotMatch(source, />编辑<\/button>/, '编辑入口不应显示文字');

console.log('web note scenarios passed');
