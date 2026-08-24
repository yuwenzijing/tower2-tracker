# 网页角色备注功能 Design QA

- Source visual truth: `C:\Users\ROG\AppData\Local\Temp\codex-clipboard-53d35c4d-c95e-48c2-8cbb-d8e2aa05f340.png`
- Implementation full screenshot: `C:\Users\ROG\Documents\永恒之塔2\业余问题\tower2-tracker\tests\artifacts\web-note-implementation.png`
- Implementation focused screenshot: `C:\Users\ROG\Documents\永恒之塔2\业余问题\tower2-tracker\tests\artifacts\web-note-card-final.png`
- Combined focused comparison: `C:\Users\ROG\Documents\永恒之塔2\业余问题\tower2-tracker\tests\artifacts\web-note-comparison.png`
- Viewport: 1365 × 1000 CSS px; responsive check at 720 × 900 CSS px
- Source pixels: 1364 × 1153; implementation full pixels: 1365 × 1000; focused implementation pixels: 1288 × 379
- Density normalization: browser device scale factor 1; comparison uses the same horizontal content scale and focuses on the shared weekly-todo/note row because the source is a component mock rather than the full production page.
- State: selected character with a saved short note; empty, editing, long-note hover and unselected states were also tested.

## Full-view comparison evidence

The production page retains its existing account and character-card composition. The note feature is confined to the existing weekly-todo title row, introduces no new section, and does not increase the character-card height. The note block is right-aligned and the edit icon remains at the row's right edge.

## Focused-region comparison evidence

The combined comparison confirms the same hierarchy as the source: unchanged weekly-todo title/count on the left, note icon and yellow note copy on the right, and a separate low-emphasis pencil control at the far right. The production density is intentionally inherited from the existing website rather than scaling the entire card to the enlarged concept mock.

## Required fidelity surfaces

- Fonts and typography: inherited the production Microsoft YaHei/PingFang stack; note text uses the existing 12 px row typography and gold semantic color. Single-line behavior is preserved.
- Spacing and layout rhythm: the row remains exactly 31 px in selected, unselected, empty, editing and responsive states. The heading is non-shrinking; the note area uses remaining width and the pencil stays 14 px from the row edge.
- Colors and visual tokens: note text uses `--gold`; edit control uses `--text-faint` and changes to `--cyan` on hover/focus; existing row background and todo-count colors are unchanged.
- Image and icon fidelity: note and pencil use the Windows Segoe MDL2 icon library, not emoji or approximate CSS drawings. Existing class artwork and card assets are unchanged.
- Copy and content: no visible “编辑” text was added. Empty selected state shows only the pencil; unselected state shows no note UI.

## Interaction verification

- Enter saves through the existing local-save and debounced cloud-sync path.
- Clicking outside saves without cancelling character selection or triggering an empty write.
- Esc cancels and restores the prior note.
- Saving an empty value removes the note and note icon while retaining the pencil.
- Notes longer than 20 Unicode characters are truncated to the 20-character viewport and animate left on hover; the pencil does not move.
- At 720 px viewport the heading remains 96 px wide, the right note area remains available, the pencil is visible, and row height remains 31 px.
- Browser console errors checked: none.

## Comparison history

1. P2 found: the initial long-note viewport could expand to 560 px, so a note longer than 20 Chinese characters might remain fully visible on a wide screen and never visibly truncate or scroll.
2. Fix: capped only the display viewport at `20em`, while leaving the inline editing input at the full 560 px available width.
3. Post-fix evidence: long-note text width 456 px, viewport width 240 px, computed transform changed during hover, row remained 31 px, and the pencil remained fixed.

## Findings

No actionable P0, P1 or P2 findings remain.

## Follow-up polish

No blocking polish items. The precise marquee speed can be tuned later from real user feedback without changing layout or data behavior.

final result: passed
