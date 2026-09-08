# Product Design QA — 圣域动态选择器

**Source visual truth**

- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-924096d6-420c-4bde-b1d3-8f6edfc0c6ba.png`（255 × 95 px）：原控件中清空 X 与系统下拉箭头重叠。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-c4cf8d05-99fb-4754-a6ba-80c04aab710a.png`（209 × 220 px）：原生系统菜单与页面深色视觉不一致。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-2d1af66b-9e2a-4547-9200-4c5e2671805e.png`（776 × 642 px）：菜单遮挡后续待办和角色卡下边界。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-ddb2af26-2c3e-49bf-b96e-a216554c7083.png`（284 × 319 px）：圣域完成态缺少与普通待办一致的方框勾选。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-841b0820-96eb-44cb-a8e2-af2a51a6b0ea.png`（761 × 251 px）：空槽箭头位置偏内。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-5ef6a4f4-1dd6-40fb-a844-a64573252970.png`（498 × 149 px）：箭头靠右、X 独立于控件右上角的目标关系。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-3ba87b02-63e0-4094-bc5d-2949a1a21536.png`：圣域行与普通待办行保持相同高度的目标状态。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-11f0ed5b-c8f3-4129-b14e-af8679712801.png`：菜单维持旧版悬浮覆盖方式的目标状态。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-cfbfeed2-6bf4-4106-b171-017785bf481f.png`：X 跨在右上边框、倒三角留在控件右内侧的目标位置。
- `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-716aa86a-bf9d-4ac5-9925-1bad172bcd22.png`（1519 × 393 px）：本轮最终目标；空槽无倒三角，X 位于已选框内右侧，圣域文字与普通待办文字对齐。
- `C:\Users\ROG\.codex\generated_images\01a08195-8ec9-77e2-92d6-18e82a299916\exec-4e557160-b95c-492f-8db6-87c909141956.png`（2170 × 725 px）：用户确认的样式 1；清除入口为无圆框、低对比度的小号 X。

**Implementation evidence**

- URL: `https://test.buyali.xyz/`
- Browser-rendered implementation screenshot: Codex in-app browser inline capture, 1935 × 1056 px, CSS desktop viewport, density 1.
- States captured and compared: three empty slots, first menu悬浮展开且行高不变、第一项选中且显示绿色方框勾选、第二菜单排除已选项，以及清空后的候选回流。
- Console errors/warnings: none.

**Full-view comparison**

- The three-column rhythm, row height, borders, type scale, and surrounding todo layout remain aligned with the existing Buyali card.
- The menu floats above later content without changing the sanctuary row height; explicit account/character/menu stacking levels keep the overlay visible.
- The selected state uses the existing semantic green token and updates the weekly count immediately.

**Focused component comparison**

- Empty and selected sanctuary controls no longer show a chevron. The 20 px circular clear control is vertically centered inside the selected slot at an 8 px right inset.
- In the selected style 1 implementation, the 20 px interaction target remains intact while the visible glyph is reduced to 12 px, removes its circle/background, and rests at 48% opacity; hover/focus restores full opacity with a subtle red tint.
- The operating-system gray menu shown in source image 2 is replaced by a navy surface with the existing border, radius, shadow, typography, cyan hover, and green selected tokens.
- The selected sanctuary now reuses the same 16 px green checkbox anatomy as awakening and other existing todo items.
- Sanctuary slots now use the same 16 px checkbox track and 6 px gap as ordinary todos, so “请选择” and selected sanctuary names share the exact text start line with “觉醒战 / 商店奥德 / 变换奥德”.
- Empty, hover/focus, expanded, selected, mutually excluded, and cleared states were exercised in the browser.

**Required fidelity surfaces**

- Fonts and typography: retained the page's PingFang SC / Microsoft YaHei / Segoe UI stack, 12 px semibold labels, and compact line height.
- Spacing and layout rhythm: preserved the three equal columns and 10 px grid gap; matched the ordinary todo's 16 px checkbox + 6 px gap; menu uses 5 px inset and 8 px option padding.
- Colors and visual tokens: uses existing `--text-dim`, `--cyan`, `--green`, and border language on a navy menu surface.
- Image/icon quality: no raster imagery is present in this component; clear and check use the project's existing Segoe MDL2 icon font.
- Copy/content: four candidate names match the requested pool; empty copy remains “请选择”.

**Findings**

- No actionable P0, P1, or P2 mismatch remains.

**Comparison history**

1. P1: first custom-menu capture was clipped by the todo/character/account card overflow. Fixed by opening overflow only on the active character and account card and raising the sanctuary row stacking level.
2. Post-fix evidence: local and deployed test captures show all four options above subsequent rows without moving the layout.
3. P2: `aria-expanded` initially serialized an empty state ambiguously. Fixed by coercing the open-state expression to a boolean; accessibility output now reports the inactive slots as collapsed and only the active slot as expanded.
4. P1: the opened menu covered later todo information. Fixed by adding an explicit expanded-row state with 154 px reserved menu space; post-fix browser evidence shows all later rows below the menu.
5. P2: selected sanctuaries lacked the established checkbox completion cue. Fixed by reusing `.todo-checkbox`; post-fix evidence shows the same green square/check treatment as ordinary weekly todos.
6. P2: the empty-slot chevron sat too close to the center. Fixed by moving it to a dedicated right-hand grid track while reserving separate clearance for the top-right X.
7. P1: reserving menu space made the sanctuary row taller than ordinary todo rows. Reverted to the established floating-menu layout, removed the expanded-row padding, and raised only the active account/character/menu stacking contexts.
8. P2: the X and chevron still read as a crowded pair. Moved the 20 px X across the top-right border and added a fixed 30 px inner clearance before the right-aligned chevron.
9. P1: the revised top-right X and chevrons still made the three-slot row visually busier than the established todo rows. Removed chevrons from both empty and selected slots and moved X inside the selected control; deployed browser evidence shows the simpler row with unchanged interaction.
10. P2: sanctuary text began 7 px to the right of ordinary todo labels because its grid used a 22 px checkbox track plus 7 px gap. Changed it to the same 16 px track plus 6 px gap used by `.todo-item`; browser evidence shows all three column labels aligned with the row below.
11. P2: the in-field circular X still competed visually with the green completion state. Implemented the user-selected style 1 by removing the border and resting background, reducing the glyph emphasis to 48% opacity, and retaining a clear hover/focus response; deployed browser evidence shows the X receding without sacrificing its click target.

**Implementation checklist**

- [x] Selection immediately marks the item complete and green.
- [x] X clears both selection and completion timestamp.
- [x] Wednesday 03:00 reset clears all three selections and timestamps.
- [x] Candidate values remain mutually exclusive across three fixed slots.
- [x] Custom menu follows the Buyali visual system and opens as an overlay without changing row height.
- [x] Open menu remains above later cards through explicit stacking order.
- [x] Selected state uses the existing green square/check completion cue.
- [x] Empty and selected slots show no dropdown chevron.
- [x] Clear X is inside the selected slot at the right edge.
- [x] Clear X uses the approved borderless, low-contrast style 1 while preserving a 20 px hit target.
- [x] Sanctuary and ordinary todo labels share the same text start line.
- [x] Test environment browser interaction and console check passed.

final result: passed
