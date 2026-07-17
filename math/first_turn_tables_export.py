"""Export the OPENING (first-turn) outcome tables to CSV for Datawrapper/Substack.

Three tables, one per roll stage of turn 1, each ranked by EXPECTED GAME TOTAL:

  roll 1  (stage A, after the initial roll, before the first reroll)
  roll 2  (stage B, after the first reroll, before the second reroll)
  roll 3  (stage C, the final roll, where you must place)  == scene 10's table

For the first two tables each row is one of the 252 distinct dice hands you could
be holding at that stage. Columns:
    Dice | Expected turn points | Most likely box | Expected game total

For the final table each row is a distinct OPTIMAL placement (box + score),
grouped exactly as scene 10 does — read straight from the committed scene-10
cache so it is identical to what's on screen. Columns:
    Dice (sample) | Box | Turn points | Expected game total

NOTHING here re-derives strategy. The expected-game-total column is pulled from
the solved value-iteration payload (ev_A / ev_B). The mid-turn "expected turn
points" and "most likely box" are obtained by propagating the ALREADY-SOLVED
optimal policy (decisions_A/B/C from the empty-state shard) forward through the
existing turn-kernel reroll matrices (REROLL_MATRIX / PAIR_TABLE) — the same
propagation build_turn_kernels uses, just seeded at a single mid-turn hand
instead of the initial-roll distribution.

Run from math/ with the ROOT venv (needs pandas/numpy):
    ../.venv/bin/python first_turn_tables_export.py
Writes exports/first_turn_tables/{roll1,reroll1,reroll2_final}.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from precomputed import ALL_DICE_STATES, dice_idx_to_values
from reduced_game_state import ReducedGameState
from state_explorer import get_state_row
from turn_kernel import REROLL_MATRIX, PAIR_TABLE, immediate_transition

N_DICE = len(ALL_DICE_STATES)               # 252
_RNG = np.arange(N_DICE)

OUT_DIR = Path("exports/first_turn_tables")
# Scene-10 committed cache (the final-roll table exactly as shown on screen).
SCENE10_CACHE = Path(__file__).resolve().parents[1] / (
    "animations/assets/first_turn_cache.json")

# Display label per math category index (matches scene 10's DISPLAY_NAMES;
# math CHANCE=11 / YAHTZEE=12).
DISPLAY_NAMES = {
    0: "Ones", 1: "Twos", 2: "Threes", 3: "Fours", 4: "Fives", 5: "Sixes",
    6: "3 of a Kind", 7: "4 of a Kind", 8: "Full House",
    9: "Sm. Straight", 10: "Lg. Straight", 11: "Chance", 12: "Yahtzee",
}


def dice_str(idx):
    return " ".join(str(int(v)) for v in dice_idx_to_values(int(idx)))


def _final_nums_from_hand(d_start, stage, dec_A, dec_B):
    """Numerators over the 252 final dice states reachable from a single hand
    d_start at the given stage, under the optimal keep policy. Returns (nums,
    denom). Reuses the turn-kernel reroll matrices; seeded one-hot at d_start."""
    if stage == "A":
        pair_A = PAIR_TABLE[_RNG, dec_A.astype(np.int32)]
        trans_A = REROLL_MATRIX[pair_A]            # (252, 252), per-row out of 7776
        after_A = trans_A[d_start]                 # one reroll: out of 7776
        pair_B = PAIR_TABLE[_RNG, dec_B.astype(np.int32)]
        trans_B = REROLL_MATRIX[pair_B]
        after_B = after_A @ trans_B                # two rerolls: out of 7776**2
        return after_B, 7776 ** 2
    if stage == "B":
        pair_B = PAIR_TABLE[_RNG, dec_B.astype(np.int32)]
        trans_B = REROLL_MATRIX[pair_B]
        after_B = trans_B[d_start]                 # one reroll: out of 7776
        return after_B, 7776
    raise ValueError("stage must be 'A' or 'B'")


def _mid_turn_table(stage, payload, row):
    """One row per dice hand at stage A/B, ranked by expected game total."""
    dec_A = payload["decisions_A"][row]
    dec_B = payload["decisions_B"][row]
    dec_C = payload["decisions_C"][row]
    ev = payload["ev_A"][row] if stage == "A" else payload["ev_B"][row]

    # Box points written for each FINAL hand under its optimal category (turn 1:
    # mask empty, no bonuses can trigger, so reward == box_points).
    box_pts = np.array([
        immediate_transition(mask=0, upper=0, eligible=False,
                             dice_idx=d2, category=int(dec_C[d2]))[0]
        for d2 in range(N_DICE)
    ], dtype=np.float64)
    cat_of = dec_C.astype(np.int64)

    rows = []
    for d in range(N_DICE):
        nums, denom = _final_nums_from_hand(d, stage, dec_A, dec_B)
        probs = nums / denom
        exp_turn = float(probs @ box_pts)
        cat_prob = np.zeros(13, dtype=np.float64)
        np.add.at(cat_prob, cat_of, probs)
        best_cat = int(np.argmax(cat_prob))
        rows.append({
            "Dice": dice_str(d),
            "Expected turn points": round(exp_turn, 2),
            "Most likely box": DISPLAY_NAMES[best_cat],
            "Expected game total": round(float(ev[d]), 2),
        })
    df = pd.DataFrame(rows).sort_values(
        "Expected game total", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", np.arange(1, len(df) + 1))
    return df


def _final_table():
    """Scene-10's grouped placement table, read from its committed cache so it
    is identical to what's on screen."""
    data = json.loads(SCENE10_CACHE.read_text())
    rows = []
    for r in data["outcomes"]:
        rows.append({
            "Dice": " ".join(str(int(v)) for v in r["dice"]),
            "Box": r["box"],
            "Turn points": r["points"],
            "Expected game total": round(float(r["ev"]), 2),
        })
    df = pd.DataFrame(rows).sort_values(
        "Expected game total", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", np.arange(1, len(df) + 1))
    return df


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    empty = ReducedGameState(filled_mask=0, upper_total=0, yahtzee_eligible=False)
    payload, row = get_state_row(empty)

    tables = {
        "roll1": _mid_turn_table("A", payload, row),
        "reroll1": _mid_turn_table("B", payload, row),
        "reroll2_final": _final_table(),
    }
    for name, df in tables.items():
        path = OUT_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"wrote {path}  ({len(df)} rows)")
        print(df.head(5).to_string(index=False))
        print()


if __name__ == "__main__":
    main()
