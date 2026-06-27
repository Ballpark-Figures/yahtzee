# Yahtzee video — specifics

Yahtzee-only conventions. The shared cross-video rules (`bpkfigures/CLAUDE.md`)
and private operational notes (`dotclaude/CLAUDE.md`) load via the two in-tree
symlink imports below — see "Config loading" at the bottom for why it's done this
way.

@CLAUDE.shared.md
@CLAUDE.private.md

---

## Script
- `animations/Script.md` is the video script — a 2-column table (voiceover |
  animation notes). Scenes `01`–`12` become `scenes/NN<name>.py`; talking-head
  segments `THA`–`THL` have no animation file. Part headers organize the game
  (negative parts count backward: −1 Endgame, −2 Middlegame, −3 Opening).
- It's reference, not a spec — see the shared "Process" notes.

## Gameplay layout (dice + scorecard)
- Use the existing machinery in `animations/assets/`: `DiceBoard`,
  `roll_lines()`, `slot_point(band, slot)`, `slot_x(slot)`, and `BAND_YS`
  (4 bands; dice roll UP from band 0 → 1 → 2 → 3, separated by 3 guide lines).
  `99test.py` is the canonical example. Default die size is `DIE_SIZE = 0.95`.
- Scorecard sits at `LEFT_SC`; dice on the right at `slot_x(...)`.

## Scorecard (`animations/assets/scorecard.py`)
- `get_scorecard(scores=None)` → empty card. `scores=[s0..s13]` → filled
  (`0..5` = Ones–Sixes, `6..12` = 3oak/4oak/full house/sm straight/lg straight/
  yahtzee/chance, `13` = yahtzee bonus).
- The Total footer bar + "Total" label ALWAYS render; the grand-total number
  only with scores.
- `show_summary=False` removes ONLY the 3rd-column CONTENTS ((63) bar, running
  totals, bottom total, grand-total number). Column outline, box scores (col 2),
  and the Total footer bar all stay.
- Columns: 1 = labels, 2 = value cells (`value_cells[0..12]`), 3 = summary. To
  place things in column 3, use the actual summary-cell center — NOT the midpoint
  to the card's panel edge (the rounded panel extends past the cells).

## Style
- Uses `bpkfigures` style + the local `config.py` for colors/fonts. The deep
  navy accent is `ACCENT_FILL` (renamed from the old battleship-ism `BOARD_FILL`).

---

## Config loading (resolved 2026-06-27)

Shared + private config reaches context through the two **in-tree symlink imports**
at the top of this file: `CLAUDE.shared.md` → `../bpkfigures/CLAUDE.md` and
`CLAUDE.private.md` → `../../dotclaude/CLAUDE.md`. This is deliberate — two harness
gotchas to NOT relearn:
- **Don't rely on working-dir auto-load.** The desktop/WSL harness injects only the
  *primary* working dir's CLAUDE.md, not additional `--add-dir` folders — so
  `bpkfigures/CLAUDE.md` being a workspace folder is not enough.
- **Don't use an out-of-tree `@../…` import.** That harness won't follow an import
  whose path escapes the project root; the in-tree symlinks dodge it.

Verified end-to-end on both machines (laptop macOS + desktop WSL/2.1.195) via a cold
"what goes into a new video's venv?" test — the private chain answered before any
file read. The symlinks are portable (same relative layout on both machines). Full
cross-machine debugging history is in git (handoff thread, log through ~`8cb1e83c`).
