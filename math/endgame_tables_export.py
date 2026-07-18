"""Export ENDGAME single-open-box tables to CSV for Datawrapper/Substack.

Setting: it's the LAST turn — exactly ONE bottom-section (lower) box is still
open. Because a lower box never touches the upper total, V is independent of the
upper total (asserted per state), so the state is pinned by just (open box,
yahtzee-bonus available?).

We tabulate two within-turn decision points, one entry per dice hand you could be
holding:
  stage A  = the OPENING roll, before the FIRST reroll   ("before_first_reroll")
  stage B  = after the first reroll, before the LAST reroll ("before_last_reroll")
(The final roll is a forced placement for a single box, so it's not tabulated.)

For every bottom box we emit a GROUPED-by-keep table at each stage in both bonus
states (available = yahtzee_eligible True, unavailable = False). The Yahtzee box
itself can't have the bonus "available" while it's open, so only the unavailable
version exists there. Small Straight additionally gets the full 252-row (per-hand)
version.

Columns (grouped): Kept dice | Probability (%) | P(<box>) (%) | Expected points
  Probability   = P(holding this hand at this stage) under optimal play, summed
                  over every hand whose optimal keep is this one,
  P(<box>)      = chance the box ends up scoring nonzero, from optimal play here,
  Expected points = EV of the remaining (only) box under optimal play, INCLUDING
                  the +100 joker-yahtzee bonus when it's available.
P and Expected points are obtained by propagating the SOLVED optimal keeps forward
through the real reroll table + box/joker score tables — for stage A that means
BOTH remaining rerolls (your chosen first keep, then the solved second keep). The
propagated EV is cross-checked against the solver's own EV (all_roll_evs) to <1e-2
(float32 EV storage).

Tables are ranked by RAW expected points (before rounding) so near-ties order
correctly.

Run from math/ with the ROOT venv (needs pandas/numpy):
    ../.venv/bin/python endgame_tables_export.py
Writes data/exports/endgame/<box>_<bonus|no_bonus>_before_{first,last}_reroll_*.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

from reduced_game_state import ReducedGameState
from state_explorer import all_roll_evs, load_payload_for_state, get_state_row
from precomputed import (REROLL_OUTCOMES, SCORE_ROWS, JOKER_SCORE_ROWS,
                         IS_YAHTZEE_T, KEEP_IDX)

# category idx -> (display name, filename slug). Bottom section = 6..12.
BOTTOM = [
    (6,  "3 of a Kind",    "three_of_a_kind"),
    (7,  "4 of a Kind",    "four_of_a_kind"),
    (8,  "Full House",     "full_house"),
    (9,  "Small Straight", "small_straight"),
    (10, "Large Straight", "large_straight"),
    (11, "Chance",         "chance"),
    (12, "Yahtzee",        "yahtzee"),
]
YAHTZEE_CAT = 12
SMALL_STRAIGHT_CAT = 9
FULL_MASK = (1 << 13) - 1
STAGES = [("A", "before_first_reroll"), ("B", "before_last_reroll")]

OUT_DIR = Path("data/exports/endgame")


def _dice_str(vals):
    return "-".join(str(int(v)) for v in vals) if len(vals) else "(reroll all)"


def _build_state(cat, eligible):
    """State with only `cat` open and the given bonus availability. Picks any
    valid upper-total row (V is upper-independent for a lower box; asserted)."""
    mask = FULL_MASK & ~(1 << cat)
    payload = load_payload_for_state(
        ReducedGameState(filled_mask=mask, upper_total=0, yahtzee_eligible=eligible))
    ye, ut, V = payload["yahtzee_eligible"], payload["upper_total"], payload["V"]
    rows = [i for i in range(len(ye)) if bool(ye[i]) == eligible]
    assert rows, f"no eligible={eligible} rows for cat {cat}"
    vals = {round(float(V[i]), 6) for i in rows}
    assert len(vals) == 1, f"cat {cat} eligible={eligible}: V varies by upper {vals}"
    return ReducedGameState(filled_mask=mask, upper_total=int(ut[rows[0]]),
                            yahtzee_eligible=eligible)


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


def _score(dist, cat, mask, eligible):
    """(P(box scores nonzero), EV) over a final-dice distribution. EV includes the
    +100 joker-yahtzee bonus when available."""
    yahtzee_filled = bool(mask & (1 << YAHTZEE_CAT))
    p_pos = ev = 0.0
    for d2, p in dist.items():
        is_joker = bool(IS_YAHTZEE_T[d2]) and yahtzee_filled
        pts = int((JOKER_SCORE_ROWS if is_joker else SCORE_ROWS)[d2][cat])
        if pts > 0:
            p_pos += p
        ev += p * pts
        if is_joker and eligible:
            ev += p * 100
    return p_pos, ev


def _rows(df, cat, mask, eligible, name, stage, dec_B, *, grouped):
    p_col = f"P({name}) (%)"

    def measured(dice_idx, keep_idx):
        return _score(_final_dist(dice_idx, keep_idx, stage, dec_B),
                      cat, mask, eligible)

    if grouped:
        groups = {}                  # keep_idx -> {"prob", "ev", "keep", "rep"}
        for _, r in df.iterrows():
            k = KEEP_IDX[tuple(int(x) for x in r["best_action_raw"])]
            g = groups.setdefault(k, {"prob": 0.0, "ev": float(r["EV"]),
                                      "keep": tuple(int(v) for v in r["best_action"]),
                                      "rep": int(r["dice_idx"])})
            g["prob"] += float(r["probability"])
            assert abs(g["ev"] - float(r["EV"])) < 1e-2, (k, g["ev"], r["EV"])
        rows = []
        for k, g in groups.items():
            p_pos, ev = measured(g["rep"], k)
            assert abs(ev - g["ev"]) < 1e-2, (name, stage, k, ev, g["ev"])
            rows.append({
                "Kept dice": _dice_str(g["keep"]),
                "Probability (%)": round(100.0 * g["prob"], 2),
                p_col: round(100.0 * p_pos, 1),
                "Expected points": round(g["ev"], 2),
                "_ev_raw": g["ev"],
            })
    else:
        rows = []
        for _, r in df.iterrows():
            k = KEEP_IDX[tuple(int(x) for x in r["best_action_raw"])]
            p_pos, ev = measured(int(r["dice_idx"]), k)
            assert abs(ev - float(r["EV"])) < 1e-2, (name, stage, r["roll"], ev, r["EV"])
            rows.append({
                "Dice": _dice_str(r["roll"]),
                "Probability (%)": round(100.0 * float(r["probability"]), 2),
                p_col: round(100.0 * p_pos, 1),
                "Expected points": round(ev, 2),
                "_ev_raw": ev,
            })
    out = pd.DataFrame(rows).sort_values(
        "_ev_raw", ascending=False).reset_index(drop=True).drop(columns="_ev_raw")
    out.insert(0, "Rank", np.arange(1, len(out) + 1))
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for cat, name, slug in BOTTOM:
        mask = FULL_MASK & ~(1 << cat)
        for eligible in (False, True):
            if cat == YAHTZEE_CAT and eligible:
                continue                          # bonus can't be live while Yahtzee open
            tag = "bonus" if eligible else "no_bonus"
            state = _build_state(cat, eligible)
            payload, row = get_state_row(state)
            dec_B = payload["decisions_B"][row]   # solved 2nd keep (used by stage A)

            for stage, infix in STAGES:
                df = all_roll_evs(state, stage=stage, sort=True)
                grp = _rows(df, cat, mask, eligible, name, stage, dec_B, grouped=True)
                gpath = OUT_DIR / f"{slug}_{tag}_{infix}_by_keep.csv"
                grp.to_csv(gpath, index=False)
                print(f"wrote {gpath.name}  ({len(grp)} keeps, "
                      f"EV {grp['Expected points'].min()}..{grp['Expected points'].max()})")

                if cat == SMALL_STRAIGHT_CAT:
                    allt = _rows(df, cat, mask, eligible, name, stage, dec_B, grouped=False)
                    apath = OUT_DIR / f"{slug}_{tag}_{infix}_all.csv"
                    allt.to_csv(apath, index=False)
                    print(f"wrote {apath.name}  ({len(allt)} hands)")


if __name__ == "__main__":
    main()
