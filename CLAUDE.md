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
  animation notes). Scenes `01`–`13` become `scenes/NN<name>.py`; talking-head
  segments `THA`–`THL` have no animation file. Part headers organize the game
  (negative parts count backward: −1 Endgame, −2 Middlegame, −3 Opening).
- **Beats within a scene are separated by a literal `---` in BOTH columns.** The
  Google-Doc→Markdown export flattens each cell to one line, so `---` is what
  preserves the beat boundaries and the voiceover↔animation pairing: split both
  cells on `---` and zip them (segment i = beat i = subscene a, b, c…). If a
  scene has several beats but NO `---`, STOP and ask for them — don't guess the
  boundaries. Full parsing/reminder rule is in the shared PREFLIGHT notes.
- It's reference, not a spec — see the shared "Process" notes.

## Gameplay layout (dice + scorecard)
- Use the existing machinery in `animations/assets/`: `DiceBoard`,
  `roll_lines()`, `slot_point(band, slot)`, `slot_x(slot)`, and `BAND_YS`
  (4 bands; dice roll UP from band 0 → 1 → 2 → 3, separated by 3 guide lines).
  `99test.py` is the canonical example. Default die size is `DIE_SIZE = 0.95`.
- Scorecard sits at `LEFT_SC`; dice on the right at `slot_x(...)`.

## Outcome grids (scenes 1 & 3)
- The 6^5 dot build-up and the 252 distinct-outcome grid enumerate with
  `_multisets` (canonical `combinations_with_replacement` order) and fill grids
  COLUMN-MAJOR — down the rows: `arrange_in_grid(..., flow_order="dr")`. Scene 1
  (`01intro.py`) is canonical; scene 3 matches it. Use the SAME `flow_order="dr"`
  ordering for EVERY grid in the video so they read consistently, and when a beat
  re-shows another scene's grid (e.g. the 252), match that scene's shape too.

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
- **`transition()` ORPHANS newly-added cell texts — don't move/fade a card you've
  `transition()`-edited (a scene-05 trap that cost ~4 render round-trips).** When
  `transition()` sets a box EMPTY→value it does `scene.add(new_text)`, so the text
  lands at SCENE top-level, NOT inside the card's VGroup. Consequences: a cell you
  mutated empty→value won't ride with the card — a later
  `card.animate.move_to(…)` leaves it FLOATING, and `FadeOut(card)` leaves it
  BEHIND. (Only empty→value cells that then persist matter: value→value changes
  use `Transform` and stay in-group; cells cleared to `None` are removed.) If you
  must move/fade a card after transition-editing it, **rebuild**: hard-clear the
  old top-level mobjects (`for m in list(self.mobjects): self.remove(m)`, keeping
  any you need) and add a FRESH `get_scorecard(...)` — an identical fresh card
  swaps in invisibly. Do NOT try to re-parent the orphan into the group mid-scene:
  a freshly-added submobject isn't re-rendered until the group is next animated,
  so it just vanishes until the next card move.

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
