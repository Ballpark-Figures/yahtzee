# Yahtzee video — specifics

Yahtzee-only conventions. The shared cross-video rules (`bpkfigures/CLAUDE.md`)
and private operational notes (`dotclaude/CLAUDE.md`) load via the two imports
below — see "Config loading" at the bottom for why it's done this way.

@CLAUDE.shared.md
@CLAUDE.private.md

> **Import canary — check this first.** If you cannot see the tokens
> `SHARED-RULES-LOADED` and `PRIVATE-RULES-LOADED` in your context, the imports
> above **silently failed** and you are missing every shared and private
> convention. The copies are machine-local and gitignored, so the usual cause is
> a repo where they were never created — a fresh clone that has not had
> `/sync-videos` run in it, so `.claude/settings.local.json` (and therefore the
> refreshing hook) does not exist yet. Recover by reading `bpkfigures/CLAUDE.md`
> and `dotclaude/CLAUDE.md` directly for this session, then regenerate the copies
> with `python3 ../../dotclaude/hooks/refresh-claude-imports.py .` and tell the
> user to run `/sync-videos`.
>
> Do **not** trust a hook that claims to inject the rules as context: a
> SessionStart hook emitting the full ~121KB gets capped by the harness, saved to
> a file, and replaced with a ~2KB preview — which contains
> `SHARED-RULES-LOADED` and so reads as success while almost everything is
> missing. The tokens only mean anything when they come from the imports.

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
  `97test.py` is the canonical example. Default die size is `DIE_SIZE = 0.95`.
- Scorecard sits at `LEFT_SC`; dice on the right at `slot_x(...)`.
- **Rolling a turn:** `place_initial` (band 0) → `first_roll` (band 1) →
  `keep(idxs)` + `roll_rest(vals)` (up to band 2) → `keep` + `roll_rest` (band 3).
  `keep()` already moves kept dice UP a band and the reroll dice to the RIGHT.
- **Illustrating a keep DECISION (no reroll)** — e.g. "here's what you'd keep":
  use `DiceBoard.show_keep(keep_idxs, base_band)` / `regroup(band)` (shared in
  `dice.py`; also module fns `show_keep_anims`/`regroup_anims`). Kept dice push
  forward one band, reroll dice go to the RIGHT, and they STAY (idempotent, so it
  morphs keep→keep). **DO NOT hand-roll this** (scene 06 reinvented it as
  `_keep_up` and got it wrong — kept dice moved up-and-back, reroll dice never
  moved right). Scene 04 is the reference user.
- **BAND = which reroll (this determines the on-screen height).** A reroll
  decision is drawn on the band of the roll you're evaluating; kept dice push up
  one band:
  - **FIRST reroll** → `base_band=1` (dice at band 1, keep → band 2). Sits LOWER
    (2 rerolls of headroom left).
  - **SECOND reroll / "last roll"** → `base_band=2` (dice at band 2, keep → band
    3, the top). Sits HIGHER.
  So the script saying "first roll" vs "last roll" for a case dictates its band.
  Match the voiceover's reroll to the band, every time.

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
- **TWO scorecards side-by-side → `get_two_scorecards(scores_l, scores_r,
  **kwargs)` + `slide_two_in(scene, left, right)`** (both in `scorecard.py`). This
  is the ONE two-card convention: FULL size at the canonical centres `TWO_L/TWO_R`
  (±3.95), entering by sliding UP from below together. Do NOT `.scale()` or
  hand-place two cards (scene 04b did and it read tiny). `**kwargs` pass through to
  each card (e.g. `fourth_column=True, fourth_width=COL4_W` for the two-player
  comparison). Reference users: scene 05 `two_cards`, 12 `compare_cards`, 04
  `avg_points_remaining`. The big right-side number + caption that often sits
  beside a left-settled card follows scene 05 `perfect_average` (one-line caption
  ABOVE a big number at NUM_POS/LBL_POS — not the cramped 2-line dice-panel label).
- The Total footer bar + "Total" label ALWAYS render; the grand-total number
  only with scores.
- `show_summary=False` removes ONLY the 3rd-column CONTENTS ((63) bar, running
  totals, bottom total, grand-total number). Column outline, box scores (col 2),
  and the Total footer bar all stay.
- **A "blank scorecard" (script term) = the START of the game, NOT a stripped
  card.** It's a NORMAL empty card WITH its 3rd column present (the (63) bar and
  0 totals) — do NOT reach for `show_summary=False`. This has bitten more than
  once (scene 12 beat a): `show_summary=False` is only for when a beat genuinely
  has no use for the summary column (e.g. its own content fills col 3).
- **The 3rd-column summary always renders full-strength.** (Removed 2026-07-06:
  the asset used to dim an incomplete section's totals to 0.5, but the scoring
  animator never re-applied it, so any *animated* card was already full — the
  dimming only ever showed on a freshly-built static mid-game card and read as
  inconsistent. Don't reintroduce it.)
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
- **Enter the card with a SHIFT, not an opacity fade.** Animating the whole card
  VGroup's opacity 0→1 (`set_opacity(0.0)` then a play back to `1.0`) corrupts the
  (63) bar: `bar_fill` starts at ~0 height, and the opacity round-trip leaves it
  rendering EMPTY/white through every later `transition()` — even though the box
  numbers + Total still update fine. It reads as "the bar turns white" and cost
  several scene-09 rounds. Slide the card in (`shift` + `animate.move_to`), the way
  scene 05 does its entrance.
- **To move the scorecard's box/bar changes IN THE SAME play as other animations**
  (e.g. fills/reveals moving simultaneously), don't call `transition()` (it
  self-`play`s). Pass your other anims as the `lead` of the card's `_animate_to(...)`
  and drive the box texts yourself — see scene 09's `_card_and` helper. (A cleaner
  fix would be an animation-returning `transition_anim()` on the asset; ASK first.)
  **But note the LEAD runs BEFORE the bar/counters** — `_animate_to` plays
  `LaggedStart(lead, moves, lag_ratio=COUNTER_LAG)` with `COUNTER_LAG=0.7`, so an
  anim you pass as the lead (e.g. an external counter) finishes as the bar is only
  starting. To make an external animation move in LOCKSTEP with the bar, set
  `card.COUNTER_LAG = 0.0` on the instance (it's a per-instance feel knob) so lead
  and bar start together — that's how scene 12 beat a syncs its expected-score
  counter to the (63) bar.
- **Card size vs the frame.** A full scorecard is ~8.46 wide × 8.30 tall, so it
  nearly fills the 16×9 frame (leaves ~0.35 margin top/bottom, comfortable width).
  Its bounding box DOES equal the visible panel — `card.get_left/right/top/bottom`
  are ACCURATE, position off them freely. (An earlier "phantom bbox" claim here was
  WRONG: the real bug was mine — I'd assumed a 14.22×8 frame; this repo's frame is
  16×9, so every margin/centring calc against the wrong bounds looked broken. See
  the shared "frame is 16×9" note.)
- **The (63) top bar is RED when the top section is COMPLETE and its sum < 63** —
  that's INTENDED (you filled the whole top and missed the 63 bonus), not a bug and
  not a flash. The real bug: the scoring/transition animator (`_animate_to`) only
  ever paints the bar blue (`ACCENT_FILL`) for sums < 63 — it never re-applies the
  red — so the moment ANY scoring animation runs, a still-complete-&-<63 top wrongly
  turns (and stays) blue. Fix is in the animator: make it match the STATIC build's
  colour logic (red for complete-&-<63). Do NOT "fix" the inconsistency by forcing
  the fill blue — that's backwards (it deletes the correct red).

## Style
- Uses `bpkfigures` style + the local `config.py` for colors/fonts. The deep
  navy accent is `ACCENT_FILL` (renamed from the old battleship-ism `BOARD_FILL`).
- **`crisp_text` WRAPS a long string.** It renders at `font_size * ss` with `ss`
  capped so the supersampled size maxes ~240pt (i.e. any `font_size ≥ 24` hits it),
  and at that size a long caption overflows the frame width and Pango silently
  line-breaks it (bit us on "Avg Top Bonus Pts"). Keep the font under ~24, OR build
  it small and `.scale()` up to the size you want — either keeps it one line. NB
  this lives in the shared `crisp_text`, so it can bite any video.

## Sourcing numbers (which venv)
- The `state_explorer`-based number queries under `math/` (e.g.
  `scene09_top_bonus_numbers.py`) need pandas/numpy/matplotlib, which live in the
  video ROOT venv `yahtzee/.venv` — NOT `math/.venv` (no pandas). Run them as
  `yahtzee/.venv/bin/python <script>.py` from `math/`; under `math/.venv` they die
  with `ModuleNotFoundError: pandas`.
- **Getting solver numbers INTO a scene — the data-module + cache convention.**
  Compute in `animations/assets/<name>_data.py`: a `_compute()` that chdirs into
  `math/`, calls `state_explorer` (the shared solver — never reinvent the math)
  and returns JSON-able data; a public fn reads a COMMITTED `<name>_cache.json`
  beside it if present, else computes + writes it, and its `__main__` unlinks +
  regenerates the cache. The SCENE does `from assets import <name>_data` and reads
  that — **render NEVER imports the solver** (it reads the committed JSON). Reference
  users: `line_data.py` (scene 08), `dp_data.py` (04), `reductions_data.py` (05).
  SEPARATELY keep a runnable `math/sceneNN_*_numbers.py` as human-readable
  provenance (scenes 06/09/12; scene 10 = `scene10_first_turn_numbers.py`). Both
  call `state_explorer`, so the query may be expressed twice but no math is
  duplicated. Do NOT bury solver queries in a scene file.

---

## Config loading (rewritten 2026-08-16 — symlinks are OUT, real copies are IN)

Shared + private config reaches context through the two `@import`s at the top of
this file. `CLAUDE.shared.md` and `CLAUDE.private.md` are **real files inside each
repo** — gitignored copies of `bpkfigures/CLAUDE.md` and `dotclaude/CLAUDE.md`,
refreshed at every session start by the SessionStart hook
`dotclaude/hooks/refresh-claude-imports.py`. Three harness rules to NOT relearn:

- **An `@import` will not resolve to a target outside the project directory — by
  ANY route.** Not `@../file.md`, not a symlink whose target points out, not a
  path into a declared additional working directory. This is the rule that
  matters, and it supersedes the old "in-tree symlinks dodge it" reading.
- **Don't rely on working-dir auto-load.** The harness injects only the *primary*
  working dir's CLAUDE.md, not additional `--add-dir` folders — so
  `bpkfigures/CLAUDE.md` being a workspace folder is not enough.
- **Don't try to inject the rules from a hook.** A SessionStart hook returning the
  full ~121KB as `additionalContext` gets capped: the harness saves it to a file
  and injects a ~2KB preview instead. The preview happens to contain
  `SHARED-RULES-LOADED`, so the canary reads GREEN while ~105KB of shared rules
  and all of the private rules are absent. The hook may only *copy files* and emit
  a one-line status.

**How this was measured (2026-08-16, WSL).** The previous scheme — committed
symlinks `CLAUDE.shared.md` → `../bpkfigures/CLAUDE.md`, `CLAUDE.private.md` →
`../../dotclaude/CLAUDE.md` — had silently stopped loading, and the recorded cause
(`\wsl$\` mangling the symlinks) was wrong. Four probes imported from
`wordle/CLAUDE.md`, all small enough to rule out any size cap, isolated it cleanly:

| probe | target | loaded? |
|---|---|---|
| `CLAUDE.tinytest.md` | real file, in-project | **yes** |
| `CLAUDE.insymtest.md` | symlink → in-project file | **yes** |
| `CLAUDE.symtest.md` | symlink → `../_import_probe.md` (out) | no |
| `@../_parent_probe.md` | plain `../` path (out), no symlink | no |

Symlinks are followed fine; escaping the project directory is what fails. Both
"out" probes were ~250 bytes, so size is not implicated. The workspace was opened
Linux-side (`vscode-remote://wsl+…`) throughout, which is what disproves the
`\wsl$\` story — that path was never involved.

Do not re-verify by "checking whether the tokens are in context" alone: that is
exactly the check the capped-hook false positive defeats. Confirm the two files
are real, non-symlink, and non-empty in the repo as well.

Superseded history: the scheme resolved 2026-06-27 (verified then on laptop macOS +
desktop WSL/2.1.195 via a cold "what goes into a new video's venv?" test) used
in-tree symlinks and did work at the time. Whether the harness tightened import
resolution later or the original verification was confounded is not established —
only that as of 2026-08-16 the symlink form does not load. Full cross-machine
debugging history is in git (handoff thread, log through ~`8cb1e83c`).
