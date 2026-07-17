"""Export the OPENING (first-turn) outcome tables to CSV for Datawrapper/Substack.

Three tables, one per roll stage of turn 1, each ranked by EXPECTED GAME TOTAL:

  roll 1  (stage A, after the initial roll, before the first reroll)
  roll 2  (stage B, after the first reroll, before the second reroll)
  roll 3  (stage C, the final roll, where you must place)  == scene 10's table

For the first two tables each row is a distinct OPTIMAL KEEP decision (the dice
you hold onto before the next reroll); the 252 hands are grouped by that keep.
Columns:
    Kept dice | Probability (%) | Expected turn points | Most likely box | Expected game total
where Probability = combined P over every hand whose optimal keep is this one
(for roll 1 that sums the raw initial-roll probabilities). The downstream values
depend ONLY on the kept dice, so they are constant across a keep group (asserted).

For the final table each row is a distinct OPTIMAL placement (box + score),
grouped exactly as scene 10 does — read straight from the committed scene-10
cache so it is identical to what's on screen. Columns:
    Box | Turn points | Dice (sample) | Probability (%) | Expected game total
(scene-10 column order for the shared columns; Probability was not in scene 10)
where Probability = P(the turn ENDS in this placement) under optimal play
(the whole (box, score) group's mass, not the single sample hand).

All probabilities come from the shared stage_dice_probs() helper (stages A/B/C).

NOTHING here re-derives strategy. The expected-game-total column is pulled from
the solved value-iteration payload (ev_A / ev_B). The mid-turn "expected turn
points" and "most likely box" are obtained by propagating the ALREADY-SOLVED
optimal policy (decisions_A/B/C from the empty-state shard) forward through the
existing turn-kernel reroll matrices (REROLL_MATRIX / PAIR_TABLE) — the same
propagation build_turn_kernels uses, just seeded at a single mid-turn hand
instead of the initial-roll distribution.

Run from math/ with the ROOT venv (needs pandas/numpy):
    ../.venv/bin/python first_turn_tables_export.py
Writes data/exports/first_turn_tables/{roll1,reroll1,reroll2_final}.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from precomputed import ALL_DICE_STATES, dice_idx_to_values
from reduced_game_state import ReducedGameState
from state_explorer import get_state_row, stage_dice_probs, keep_to_values
from turn_kernel import REROLL_MATRIX, PAIR_TABLE, immediate_transition

N_DICE = len(ALL_DICE_STATES)               # 252
_RNG = np.arange(N_DICE)

OUT_DIR = Path("data/exports/first_turn_tables")
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


def _box_pts_and_cat(dec_C):
    """Per FINAL hand: (box points written, optimal category) under the policy.
    Turn 1 has an empty mask so no bonus can trigger; reward == box_points."""
    box_pts = np.array([
        immediate_transition(mask=0, upper=0, eligible=False,
                             dice_idx=d2, category=int(dec_C[d2]))[0]
        for d2 in range(N_DICE)
    ], dtype=np.float64)
    return box_pts, dec_C.astype(np.int64)


def _keep_group_table(stage, empty, payload, row, box_pts, cat_of):
    """One row per distinct optimal KEEP at stage A/B (the 252 hands grouped by
    the dice kept), ranked by expected game total. The kept dice fully determine
    the future, so expected turn points / most likely box / expected game total
    are constant across a keep group; Probability sums over the group's hands."""
    dec_A = payload["decisions_A"][row]
    dec_B = payload["decisions_B"][row]
    dec = dec_A if stage == "A" else dec_B
    ev = payload["ev_A"][row] if stage == "A" else payload["ev_B"][row]
    reach = stage_dice_probs(empty, stage)   # P(hold each hand at this stage)

    groups = {}                              # keep_idx -> [hand dice_idx, ...]
    for d in range(N_DICE):
        groups.setdefault(int(dec[d]), []).append(d)

    rows = []
    raw_total = 0.0                          # unrounded mass, for the partition check
    for keep_idx, hands in groups.items():
        rep = hands[0]                       # any hand in the group (same future)
        nums, denom = _final_nums_from_hand(rep, stage, dec_A, dec_B)
        probs = nums / denom
        exp_turn = float(probs @ box_pts)
        cat_prob = np.zeros(13, dtype=np.float64)
        np.add.at(cat_prob, cat_of, probs)
        best_cat = int(np.argmax(cat_prob))
        ev_group = float(ev[rep])
        assert max(abs(float(ev[h]) - ev_group) for h in hands) < 1e-4, keep_idx
        group_p = float(sum(reach[h] for h in hands))
        raw_total += group_p
        kept = keep_to_values(keep_idx)
        rows.append({
            "Kept dice": "-".join(str(int(v)) for v in kept) if kept else "(reroll all)",
            "Probability (%)": round(100.0 * group_p, 1),
            "Expected turn points": round(exp_turn, 2),
            "Most likely box": DISPLAY_NAMES[best_cat],
            "Expected game total": round(ev_group, 1),
        })
    assert abs(raw_total - 1.0) < 1e-3, f"{stage} keep mass = {raw_total}"
    df = pd.DataFrame(rows).sort_values(
        "Expected game total", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", np.arange(1, len(df) + 1))
    return df


def _final_table(empty, box_pts, cat_of):
    """Scene-10's grouped placement table, read from its committed cache so it
    is identical to what's on screen. Probability = P(the turn ends in this
    (box, score) placement) under optimal play = the group's stage-C mass."""
    p_C = stage_dice_probs(empty, "C")
    group_prob = {}                              # (category_idx, box_points) -> P
    for d2 in range(N_DICE):
        key = (int(cat_of[d2]), int(box_pts[d2]))
        group_prob[key] = group_prob.get(key, 0.0) + float(p_C[d2])

    data = json.loads(SCENE10_CACHE.read_text())
    rows = []
    raw_total = 0.0                          # unrounded mass, for the partition check
    for r in data["outcomes"]:
        prob = group_prob[(int(r["cat"]), int(r["points"]))]
        raw_total += prob
        rows.append({
            # scene-10 column order (Box | Points | Dice | Avg game total), with
            # Probability (not shown in scene 10) inserted before the game total.
            "Box": r["box"],
            "Turn points": r["points"],
            "Dice": "-".join(str(int(v)) for v in r["dice"]),
            "Probability (%)": round(100.0 * prob, 1),
            "Expected game total": round(float(r["ev"]), 1),
        })
    assert abs(raw_total - 1.0) < 1e-3, f"final placement mass = {raw_total}"
    df = pd.DataFrame(rows).sort_values(
        "Expected game total", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", np.arange(1, len(df) + 1))
    return df


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    empty = ReducedGameState(filled_mask=0, upper_total=0, yahtzee_eligible=False)
    payload, row = get_state_row(empty)
    box_pts, cat_of = _box_pts_and_cat(payload["decisions_C"][row])

    tables = {
        "roll1": _keep_group_table("A", empty, payload, row, box_pts, cat_of),
        "reroll1": _keep_group_table("B", empty, payload, row, box_pts, cat_of),
        "reroll2_final": _final_table(empty, box_pts, cat_of),
    }
    for name, df in tables.items():
        total_p = float(df["Probability (%)"].sum())   # rounded; ~100 modulo drift
        path = OUT_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"wrote {path}  ({len(df)} rows, rounded Probability sums to {total_p:.1f}%)")
        print(df.head(5).to_string(index=False))
        print()


if __name__ == "__main__":
    main()
