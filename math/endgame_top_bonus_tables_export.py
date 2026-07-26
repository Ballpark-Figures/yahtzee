"""Export a single-open-box endgame table for ANY box + upper total, to CSV.

Companion to ``endgame_tables_export.py``, which handles LOWER boxes only (where V
is independent of the upper total, so it need not be specified). This one takes the
upper total as an argument, so it also covers an UPPER box as the last open box —
where the upper total is the whole point: filling the box can push the top section
across 63 and earn the +35 top bonus, so V depends on it.

    Example (Threes open, 54 already in the top): 54 + three 3s = 63, so you clear
    the bonus iff you end with at least three 3s. That threshold makes the EV jump.

It tabulates the same two within-turn decision points as the lower-box endgame set,
one entry per keep under optimal play:
  stage A  = the OPENING roll, before the FIRST reroll   ("before_first_reroll")
  stage B  = after the first reroll, before the LAST reroll ("before_last_reroll")
(The final roll is a forced placement into the single open box, so it isn't tabulated.)

Both Yahtzee-bonus states are emitted where legal (available = a 50 is already in the
Yahtzee box, so a Yahtzee adds the +100 joker bonus; unavailable = it doesn't). The
Yahtzee box itself can't be bonus-eligible while open, so only the unavailable version
exists there.

Columns (grouped, matching the lower-box tables):
  Kept dice | Probability (%) | P(<box>) (%) | Expected points
  Probability     = P(holding a hand whose optimal keep is this one) at this stage,
  P(<box>)        = chance the box ends up scoring nonzero from here,
  Expected points = EV of the remaining (only) box under optimal play, INCLUDING the
                    +35 top bonus (when the upper total would cross 63) and the +100
                    joker bonus (when available).

Every EV is SOURCED, not computed here. The machinery is the same ``state_explorer``
the notebook uses: the "Expected points" per keep-group is the solver's own ev_A/ev_B
(via ``all_roll_evs``), and the propagated cross-check reward uses
``immediate_reward_for_category_choice`` (the house helper that applies the +35/+100
bonuses). The propagated EV is checked against the solver's EV to <1e-2 (float32 EV
storage); a mismatch aborts the export.

Tables are ranked by RAW expected points (before rounding) so near-ties order right.

Run from math/ with the ROOT venv (needs pandas/numpy):
    ../.venv/bin/python endgame_top_bonus_tables_export.py Threes 54
    ../.venv/bin/python endgame_top_bonus_tables_export.py "Full House" 0
Category may be a CATEGORY_NAMES name or an index 0..12. Writes to
    data/exports/endgame/<slug>_at<upper>_<bonus|no_bonus>_before_{first,last}_reroll_by_keep.csv
"""
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from constants import CATEGORY_NAMES
from reduced_game_state import ReducedGameState
from state_explorer import (all_roll_evs, get_state_row,
                            immediate_reward_for_category_choice)
from precomputed import (REROLL_OUTCOMES, SCORE_ROWS, JOKER_SCORE_ROWS,
                         IS_YAHTZEE_T, KEEP_IDX)

YAHTZEE_CAT = 12
FULL_MASK = (1 << 13) - 1
STAGES = [("A", "before_first_reroll"), ("B", "before_last_reroll")]

OUT_DIR = Path("data/exports/endgame")


def _resolve_category(category):
    """Accept a CATEGORY_NAMES name or an int index; return the int index."""
    if isinstance(category, str) and not category.lstrip("-").isdigit():
        return CATEGORY_NAMES.index(category)
    return int(category)


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _dice_str(vals):
    return "-".join(str(int(v)) for v in vals) if len(vals) else "(reroll all)"


def _final_dist(dice_idx, keep_idx, stage, dec_B):
    """Distribution over FINAL dice from holding `dice_idx` and keeping `keep_idx`.
    Stage B: one reroll (place next). Stage A: this reroll, then the solved second
    keep (dec_B), then reroll again."""
    finals, nums = REROLL_OUTCOMES[(int(dice_idx), int(keep_idx))]
    dist = {}
    if stage == "B":
        for d1, n1 in zip(finals, nums):
            dist[int(d1)] = dist.get(int(d1), 0.0) + n1 / 7776.0
    else:  # stage A: one more optimal (dec_B) reroll before placing
        for d1, n1 in zip(finals, nums):
            w1 = n1 / 7776.0
            f2, n2s = REROLL_OUTCOMES[(int(d1), int(dec_B[int(d1)]))]
            for d2, n2 in zip(f2, n2s):
                dist[int(d2)] = dist.get(int(d2), 0.0) + w1 * (n2 / 7776.0)
    return dist


def _score(dist, state, cat, mask):
    """(P(box scores nonzero), EV) over a final-dice distribution. EV comes from the
    house helper immediate_reward_for_category_choice, so it includes the +35 top
    bonus (when the upper total crosses 63) and the +100 joker bonus when available."""
    yahtzee_filled = bool(mask & (1 << YAHTZEE_CAT))
    p_pos = ev = 0.0
    for d2, p in dist.items():
        is_joker = bool(IS_YAHTZEE_T[d2]) and yahtzee_filled
        pts = int((JOKER_SCORE_ROWS if is_joker else SCORE_ROWS)[d2][cat])
        if pts > 0:
            p_pos += p
        ev += p * immediate_reward_for_category_choice(state, d2, cat)
    return p_pos, ev


def _rows(df, state, cat, mask, name, stage, dec_B):
    p_col = f"P({name}) (%)"

    groups = {}                      # keep_idx -> {"prob", "ev", "keep", "rep"}
    for _, r in df.iterrows():
        k = KEEP_IDX[tuple(int(x) for x in r["best_action_raw"])]
        g = groups.setdefault(k, {"prob": 0.0, "ev": float(r["EV"]),
                                  "keep": tuple(int(v) for v in r["best_action"]),
                                  "rep": int(r["dice_idx"])})
        g["prob"] += float(r["probability"])
        assert abs(g["ev"] - float(r["EV"])) < 1e-2, (k, g["ev"], r["EV"])
    rows = []
    for k, g in groups.items():
        p_pos, ev = _score(_final_dist(g["rep"], k, stage, dec_B), state, cat, mask)
        assert abs(ev - g["ev"]) < 1e-2, (name, stage, k, ev, g["ev"])
        rows.append({
            "Kept dice": _dice_str(g["keep"]),
            "Probability (%)": round(100.0 * g["prob"], 2),
            p_col: round(100.0 * p_pos, 1),
            "Expected points": round(g["ev"], 2),
            "_ev_raw": g["ev"],
        })
    out = pd.DataFrame(rows).sort_values(
        "_ev_raw", ascending=False).reset_index(drop=True).drop(columns="_ev_raw")
    out.insert(0, "Rank", np.arange(1, len(out) + 1))
    return out


def export_case(category, upper_total, out_dir=OUT_DIR):
    """Write the endgame keep tables for `category` as the last open box with
    `upper_total` already scored in the top section. Returns the paths written."""
    cat = _resolve_category(category)
    name = CATEGORY_NAMES[cat]
    slug = _slug(name)
    mask = FULL_MASK & ~(1 << cat)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for eligible in (False, True):
        if cat == YAHTZEE_CAT and eligible:
            continue                          # bonus can't be live while Yahtzee open
        tag = "bonus" if eligible else "no_bonus"
        state = ReducedGameState(filled_mask=mask, upper_total=int(upper_total),
                                 yahtzee_eligible=eligible)
        try:
            payload, row = get_state_row(state)
        except KeyError as e:
            print(f"SKIP {slug} at {upper_total} ({tag}): no solved row ({e})")
            continue
        dec_B = payload["decisions_B"][row]   # solved 2nd keep (used by stage A)

        for stage, infix in STAGES:
            df = all_roll_evs(state, stage=stage, sort=True)
            grp = _rows(df, state, cat, mask, name, stage, dec_B)
            gpath = out_dir / f"{slug}_at{upper_total}_{tag}_{infix}_by_keep.csv"
            grp.to_csv(gpath, index=False)
            written.append(gpath)
            print(f"wrote {gpath.name}  ({len(grp)} keeps, "
                  f"EV {grp['Expected points'].min()}..{grp['Expected points'].max()})")
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("category", help="box name (e.g. Threes, 'Full House') or index 0..12")
    ap.add_argument("upper_total", type=int, help="points already scored in the top section")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help=f"output dir (default {OUT_DIR})")
    args = ap.parse_args()
    export_case(args.category, args.upper_total, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
