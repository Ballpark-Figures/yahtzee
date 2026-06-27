# Yahtzee video — specifics

Yahtzee-only conventions. The shared cross-video rules live in
`bpkfigures/CLAUDE.md` (auto-loaded since bpkfigures is always in the workspace).

<!-- ===================================================================== -->
<!-- TEMPORARY BOOTSTRAP — delete this block once the desktop is set up.    -->
<!-- It lives HERE (yahtzee/CLAUDE.md) because yahtzee is its own git repo  -->
<!-- and this file is the ONE thing the desktop is known to have. The       -->
<!-- desktop does NOT yet have the umbrella repo or dotclaude, so the        -->
<!-- bootstrap has to fetch both.                                            -->
<!-- ===================================================================== -->
## ⚠️ TEMP: Bootstrap this machine (desktop setup)

**On the desktop, tell the agent: "run the bootstrap in yahtzee/CLAUDE.md".**

**The situation.** This machine has the **`yahtzee`** repo (its own repo:
`github.com/Ballpark-Figures/yahtzee`) but is missing two things that everything
else depends on:
- the **umbrella `Ballpark-Figures` repo** — which contains the shared
  **`bpkfigures/`** package and `bpkfigures/CLAUDE.md`. (`bpkfigures` is NOT a
  separate clone; it's tracked inside the umbrella repo.)
- the **`dotclaude` repo** (`github.com/Ballpark-Figures/dotclaude`) — which holds
  the private CLAUDE.md, the slash commands, and the settings allowlist. Three
  symlinks point into it; without it they dangle and the private content silently
  vanishes.

**Target layout** — three repos as siblings under one parent dir (on this desktop
that parent is wherever you want them, e.g. `/projects/`). `yahtzee` normally lives
*inside* the umbrella, but if it's currently standalone, see step 2:
```
<parent>/
├── Ballpark-Figures/      (umbrella: contains bpkfigures/, .claude/, battleship/, yahtzee/)
│   └── yahtzee/           (this repo, nested in the umbrella)
└── dotclaude/             (private: CLAUDE.md, commands/, settings.local.json)
```

**Steps** (the agent should adapt absolute paths to wherever you keep projects):

1. **Clone the umbrella repo** into the parent dir:
   ```sh
   git clone https://github.com/Ballpark-Figures/ballpark-figures.git
   ```
   This brings down `bpkfigures/` (and its CLAUDE.md), plus the `.claude/` dir.
   The umbrella also nests `yahtzee/` — clone it inside if it isn't already:
   `cd Ballpark-Figures && git clone https://github.com/Ballpark-Figures/yahtzee.git`
   (or move/relocate your existing standalone yahtzee clone to `Ballpark-Figures/yahtzee`).

2. **Clone `dotclaude` as a sibling of `Ballpark-Figures`** (same parent dir):
   ```sh
   git clone https://github.com/Ballpark-Figures/dotclaude.git
   ```
   Result: `<parent>/Ballpark-Figures/` and `<parent>/dotclaude/` side by side.
   This sibling relationship is the one thing the symlinks below REQUIRE.

3. **Recreate the three symlinks** with RELATIVE paths (so they're portable across
   machines regardless of the absolute parent). Run from the **root of the
   `Ballpark-Figures` umbrella repo**:
   ```sh
   mkdir -p .claude
   ln -sfn ../../dotclaude/CLAUDE.md              bpkfigures/CLAUDE.private.md
   ln -sfn ../../../dotclaude/commands            .claude/commands
   ln -sfn ../../../dotclaude/settings.local.json .claude/settings.local.json
   ```
   `../` counts: `bpkfigures/` and `.claude/` are each one level into the repo, and
   the repo root is one level under the shared parent — so it's `../../dotclaude/...`
   from `bpkfigures/` and `../../../dotclaude/...` from `.claude/`. Verify each with
   `ls -l <link>`; the arrow target must resolve (no "No such file or directory").

4. **Verify** in a fresh `claude` session, asking cold before reading any file:
   "What's my gh account name?" → should answer **MathNCheese** straight from
   context. That confirms the private import resolved.

5. **Done? Delete this block** from `yahtzee/CLAUDE.md` and commit/push, so it stops
   shipping to every machine.

### Verification checklist (run after the steps; each line is pass/fail)

Tick these off — if all pass, the desktop is fully wired. The last one is the real
test; the rest explain *why* if it fails.

- [ ] **Repos present & sibling layout.** `Ballpark-Figures/` and `dotclaude/` sit
      in the SAME parent dir. Check: from the umbrella root, `ls -d ../dotclaude`
      resolves.
- [ ] **`bpkfigures/` came down with the umbrella.** Check: `ls bpkfigures/CLAUDE.md`
      exists (it's tracked inside the umbrella, not a separate clone).
- [ ] **Umbrella is up to date.** The import line must be present:
      `grep '@CLAUDE.private.md' bpkfigures/CLAUDE.md` returns a hit. If not,
      `git pull` in the umbrella (the activating commit is `4b24e0e`).
- [ ] **Three symlinks resolve** (no "No such file or directory" from `ls -l`):
      `bpkfigures/CLAUDE.private.md`, `.claude/commands`, `.claude/settings.local.json`.
- [ ] **Slash commands load.** Type `/` in a session → `new-video` and `sync-videos`
      appear. (Confirms `.claude/commands` symlink.)
- [ ] **Allowlist active.** A trivial project-file edit does NOT prompt for
      permission. (Confirms `.claude/settings.local.json` symlink.)
- [ ] **Public conventions load.** Agent knows yahtzee terms cold (`DiceBoard`,
      `slot_x`, `ACCENT_FILL`). (Confirms `bpkfigures/CLAUDE.md` loads.)
- [ ] **★ Private import loads (THE real test).** Fresh session, asked cold before
      reading any file: "What's my gh account name?" → **MathNCheese**. If yes, the
      `@CLAUDE.private.md` import resolved and the whole chain works.

If the ★ test fails but the symlinks resolve, the usual cause is the umbrella
wasn't pulled (no import line) — re-check the third box.

<!-- ===================================================================== -->
<!-- END TEMPORARY BOOTSTRAP                                                -->
<!-- ===================================================================== -->

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
