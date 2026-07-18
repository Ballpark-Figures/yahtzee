"""Export ENDGAME single-open-box tables to CSV for Datawrapper/Substack.

First endgame state: it's the last turn, the ONLY unfilled box is Small Straight,
and no Yahtzee bonus is available (yahtzee_eligible=False, i.e. you never scored a
50 in the Yahtzee box). We tabulate STAGE B — after the first reroll, before the
LAST (second) reroll — one entry per dice hand you could be holding.

Because Small Straight is a LOWER box, filling it can't change the upper total, so
V is identical across every upper-total row of this mask (verified: 18.4807) — the
state is well-defined without specifying the upper total.

Two CSVs (both ranked by raw expected points, before rounding):
  ..._all.csv      one row per distinct dice hand (252)
  ..._by_keep.csv  the hands grouped by their optimal keep (the dice you hold)

Columns:
  Dice / Kept dice | Probability (%) | P(small straight) (%) | Expected points
where
  Probability      = P(holding this hand at stage B) under optimal play (the keep
                     version sums it over every hand with that optimal keep),
  P(small straight) = chance you still score the straight from here = EV / 30
                     (30 is the only nonzero outcome; a joker yahtzee also scores
                     30, but with no bonus since yahtzee_eligible=False),
  Expected points  = EV of the remaining (only) box under optimal play.

Nothing here re-derives strategy: EV / probability / keep come straight from the
solved policy via state_explorer.all_roll_evs(state, stage="B").

Run from math/ with the ROOT venv (needs pandas/numpy):
    ../.venv/bin/python endgame_tables_export.py
Writes data/exports/endgame/small_straight_before_last_reroll_{all,by_keep}.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

from reduced_game_state import ReducedGameState
from state_explorer import all_roll_evs

# ── The endgame state ──────────────────────────────────────────────────────────
OPEN_CATEGORY = 9            # Small Straight (constants.py order)
OPEN_NAME = "Small Straight"
BOX_MAX = 30                 # the only nonzero score for this box
YAHTZEE_ELIGIBLE = False     # no Yahtzee bonus available
STAGE = "B"                  # before the last reroll

FULL_MASK = (1 << 13) - 1
MASK = FULL_MASK & ~(1 << OPEN_CATEGORY)

OUT_DIR = Path("data/exports/endgame")
STEM = "small_straight_before_last_reroll"


def _dice_str(vals):
    return "-".join(str(int(v)) for v in vals)


def _state():
    # upper_total is irrelevant here (lower box), so 0 is as good as any.
    return ReducedGameState(filled_mask=MASK, upper_total=0,
                            yahtzee_eligible=YAHTZEE_ELIGIBLE)


def _all_table(df):
    """One row per dice hand, ranked by raw expected points."""
    rows = []
    for _, r in df.iterrows():
        ev = float(r["EV"])
        rows.append({
            "Dice": _dice_str(r["roll"]),
            "Probability (%)": round(100.0 * float(r["probability"]), 2),
            "P(small straight) (%)": round(100.0 * ev / BOX_MAX, 1),
            "Expected points": round(ev, 2),
            "_ev_raw": ev,
        })
    out = pd.DataFrame(rows).sort_values(
        "_ev_raw", ascending=False).reset_index(drop=True).drop(columns="_ev_raw")
    out.insert(0, "Rank", np.arange(1, len(out) + 1))
    return out


def _by_keep_table(df):
    """Hands grouped by their optimal keep, ranked by raw expected points. The
    kept dice fully determine the future, so EV is constant within a keep group
    (asserted); Probability sums over the group's hands."""
    groups = {}                  # keep tuple -> {"prob", "ev", "evs"}
    for _, r in df.iterrows():
        keep = tuple(int(v) for v in r["best_action"])
        ev = float(r["EV"])
        g = groups.setdefault(keep, {"prob": 0.0, "ev": ev, "evs": []})
        g["prob"] += float(r["probability"])
        g["evs"].append(ev)

    rows = []
    for keep, g in groups.items():
        assert max(g["evs"]) - min(g["evs"]) < 1e-6, (keep, g["evs"])
        ev = g["ev"]
        rows.append({
            "Kept dice": _dice_str(keep) if keep else "(reroll all)",
            "Probability (%)": round(100.0 * g["prob"], 2),
            "P(small straight) (%)": round(100.0 * ev / BOX_MAX, 1),
            "Expected points": round(ev, 2),
            "_ev_raw": ev,
        })
    out = pd.DataFrame(rows).sort_values(
        "_ev_raw", ascending=False).reset_index(drop=True).drop(columns="_ev_raw")
    out.insert(0, "Rank", np.arange(1, len(out) + 1))
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = all_roll_evs(_state(), stage=STAGE, sort=True)

    tables = {
        f"{STEM}_all": _all_table(df),
        f"{STEM}_by_keep": _by_keep_table(df),
    }
    for name, tbl in tables.items():
        total_p = float(tbl["Probability (%)"].sum())
        path = OUT_DIR / f"{name}.csv"
        tbl.to_csv(path, index=False)
        print(f"wrote {path}  ({len(tbl)} rows, Probability sums to {total_p:.2f}%)")
        print(tbl.head(6).to_string(index=False))
        print()


if __name__ == "__main__":
    main()
