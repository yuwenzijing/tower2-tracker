import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const source = await fs.readFile(new URL('../public/index.html', import.meta.url), 'utf8');

assert.match(source, /SANCTUARY_OPTIONS\s*=\s*\['卢德莱', '侵蚀净化所', '穆斯费尔圣杯', '悲叹雪原'\]/,
  '圣域候选池必须包含四个指定项目');
assert.match(source, /SANCTUARY_SLOTS\s*=\s*\[[\s\S]*sanctuary1Name[\s\S]*sanctuary2Name[\s\S]*sanctuary3Name/,
  '必须固定保留三个选择槽位');
assert.match(source, /selectedElsewhere[\s\S]*selectedElsewhere\.indexOf\(name\) === -1/,
  '其他槽位已选项目必须从候选项中排除');
assert.match(source, /function clearSanctuarySelection[\s\S]*setSanctuarySelection\(accId, charId, slotKey, ''\)/,
  '每个槽位必须能够清空');
assert.match(source, /r\.ch\[TODO_CONFIG\[slotKey\]\.field\]\s*=\s*next \? new Date\(\)\.toISOString\(\) : null/,
  '选择项目必须立即写入完成时间，清空时必须删除完成时间');
assert.match(source, /function ensureSanctuaryWeek[\s\S]*ch\[slot\.nameField\] = null[\s\S]*ch\[TODO_CONFIG\[slot\.key\]\.field\] = null/,
  '每周重置必须同时清空选项和完成时间');
assert.match(source, /if \(ch\.sanctuary1Name === undefined\) ch\.sanctuary1Name = isTodoDone/,
  '旧数据只应迁移本周已经完成的固定项目');
assert.match(source, /class="sanctuary-menu"[\s\S]*class="sanctuary-option/,
  '必须使用与页面一致的自定义菜单替代系统原生下拉框');
assert.doesNotMatch(source, /class="sanctuary-slot[\s\S]{0,500}<select/,
  '圣域槽位不应继续使用系统原生 select');
assert.doesNotMatch(source, /sanctuary-row\.menu-open|padding-bottom:\s*154px/,
  '菜单展开时不得改变圣域行高');
assert.match(source, /account-card\.sanctuary-menu-open[^}]*z-index:\s*40[\s\S]*char-card\.sanctuary-menu-open[^}]*z-index:\s*50[\s\S]*sanctuary-menu\s*\{[\s\S]*z-index:\s*100/,
  '菜单必须通过明确的堆叠顺序悬浮在后续卡片之上');
assert.match(source, /<span class="todo-checkbox" aria-hidden="true">' \+ \(done \? '✓' : ''\)/,
  '圣域完成态必须沿用现有方框勾选组件');
assert.doesNotMatch(source, /sanctuary-chevron/,
  '圣域选择器不得再显示下拉倒三角');
assert.match(source, /\.todo-item\.sanctuary-slot[\s\S]*grid-template-columns:\s*16px minmax\(0, 1fr\)[\s\S]*gap:\s*6px/,
  '圣域复选框和文字必须沿用普通待办的 16px + 6px 对齐节奏');
assert.match(source, /\.sanctuary-clear[\s\S]*right:\s*8px[\s\S]*top:\s*50%[\s\S]*translateY\(-50%\)/,
  '清空按钮必须位于选择框内部右侧并垂直居中');
assert.match(source, /\.sanctuary-clear[\s\S]*border:\s*0[\s\S]*background:\s*transparent[\s\S]*opacity:\s*\.48/,
  '清空按钮静态状态必须使用低对比度无圆框样式');
assert.match(source, /\$\{renderSanctuarySlot\(acc, ch, SANCTUARY_SLOTS\[0\], s1Done\)\}[\s\S]*SANCTUARY_SLOTS\[2\]/,
  '角色卡必须只渲染三个动态圣域槽位');

console.log('web sanctuary scenarios passed');
