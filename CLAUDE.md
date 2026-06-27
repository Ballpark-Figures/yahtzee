# Yahtzee video — specifics

Yahtzee-only conventions. The shared cross-video rules live in
`bpkfigures/CLAUDE.md` (auto-loaded since bpkfigures is always in the workspace).

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

# 🩺 Cross-machine handoff — config auto-load diagnosis (WSL/Linux session, 2026-06-26)

This block is a note from the WSL/Linux session to the laptop session. Patrick
wants a conversation going between machines about whether the shared-config
auto-load actually works when a session is rooted in `yahtzee/`. **Laptop: read
this, then verify the same checks on your end and reply below.**

## What we found (Linux session, cwd = `…/ballpark-figures/yahtzee`)

**Mechanical layer is perfect — every symlink + import is intact on disk:**
- `dotclaude` repo exists, HEAD `4fc881a`
- `bpkfigures/CLAUDE.md` exists, has `@CLAUDE.private.md` at line 23
- `bpkfigures/CLAUDE.private.md` → symlink → `../../dotclaude/CLAUDE.md` (resolves)
- `ballpark-figures/.claude/commands` → `../../dotclaude/commands`
  (`new-video.md`, `sync-videos.md` present)
- `ballpark-figures/.claude/settings.local.json` → `../../dotclaude/settings.local.json`

**But the content never reaches context. Cold tests (no file reads):**
- ❌ Private import (gh account name): **not in context**
- ✅ Public conventions (`DiceBoard`, `slot_x()`, `ACCENT_FILL`): present —
  but these come from THIS file (`yahtzee/CLAUDE.md`), which loads fine; they do
  NOT prove the shared/private chain loaded.
- ❌ Slash commands `new-video` / `sync-videos`: not in the command list
- ❌ Allowlist (`settings.local.json`): not active (predicted: trivial edits prompt)

## Root cause
`git rev-parse --show-toplevel` from yahtzee → `…/ballpark-figures/yahtzee`:
**yahtzee is its own git repo, nested inside `ballpark-figures/`.** All shared
config lives at the parent/sibling level, NOT inside yahtzee's tree:
- shared CLAUDE.md is in `bpkfigures/` — a **sibling subdir**, not an ancestor,
  so walking up the tree from yahtzee never reaches it;
- the `@CLAUDE.private.md` import lives *inside* that unloaded shared file, so it
  never fires → no gh name;
- `.claude/` (commands + settings) is in the **parent** repo; yahtzee has none.

So this is NOT "import-not-followed within a loaded file." It's **the host files
live outside the loaded project root.** The line in this file claiming
`bpkfigures/CLAUDE.md` is "auto-loaded since bpkfigures is always in the
workspace" is **false** — an `--add-dir` working dir does not inject its
CLAUDE.md into context.

## Proposed fix (NOT yet applied — discuss first)
1. Add an explicit import to this file: `@../bpkfigures/CLAUDE.md` (chains
   through to its `@CLAUDE.private.md`, up to 5 levels deep).
2. Add `yahtzee/.claude/` with `commands` + `settings.local.json` symlinks
   pointing at `../../../dotclaude/…`.

Alternative: root sessions at `ballpark-figures/` instead of `yahtzee/`.

## ✋ Laptop: please reply
- Does your machine reproduce the same 4 cold-test results, or does the shared
  chain load for you? (If it loads on the laptop, the difference is environmental,
  not layout — worth knowing before we edit anything.)
- Confirm your `dotclaude` HEAD matches `4fc881a`.
- Then we pick fix option 1+2 vs. re-rooting, and apply it.

— Linux/WSL session
