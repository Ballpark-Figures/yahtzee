"""Scene 10 (first turn) — provenance for the "Average Points by Roll" list.

Each ROW of the scrolling list is a distinct OPTIMAL first-turn outcome
(box + score), ranked by expected FINAL game total. For every one of the 252
distinct final rolls we ask the solved policy what the best category placement
is and what it's worth:

    category_alternatives(empty_state, roll).iloc[0]
      -> (optimal category, score_points, total_EV)

where total_EV = immediate_reward (banked points, incl. any bonus) + V(resulting
reduced state). This is the SAME recipe scene 12 used (points + V(state)); nothing
here re-derives strategy — it reads the solved V / policy.

Then we GROUP rolls by their (optimal category, score) — e.g. 14444 and 44446
both land on Fours=16 — so each group is one list row. total_EV is identical
across a group (same resulting state), and the SAMPLE DICE is the
lexicographically-first sorted roll in the group.

Run from math/ with the ROOT venv (needs pandas/numpy):
    ../.venv/bin/python scene10_first_turn_numbers.py
"""
import numpy as np

from constants import *
from precomputed import ALL_DICE_STATES, dice_idx_to_values, SCORE_ROWS
from reduced_game_state import ReducedGameState
from state_explorer import state_value, category_alternatives, cat_name


def main():
    empty = ReducedGameState(filled_mask=0, upper_total=0, yahtzee_eligible=False)
    v_empty = state_value(empty)
    print(f"V(empty) whole-game expected score = {v_empty:.4f}\n")

    # groups keyed by (category_idx, score_points)
    groups = {}   # key -> {"evs": set, "rolls": [sorted tuple, ...]}
    for idx in range(len(ALL_DICE_STATES)):
        vals = tuple(dice_idx_to_values(idx))          # sorted-ascending roll
        top = category_alternatives(empty, idx).iloc[0]
        key = (int(top["category_idx"]), int(top["score_points"]))
        g = groups.setdefault(key, {"evs": set(), "rolls": []})
        g["evs"].add(round(float(top["total_EV"]), 6))
        g["rolls"].append(vals)

    rows = []
    for (cat, pts), g in groups.items():
        ev = float(np.mean(list(g["evs"])))
        assert max(g["evs"]) - min(g["evs"]) < 1e-4, (cat, pts, g["evs"])
        sample = min(g["rolls"])                        # lexicographically first
        rows.append((ev, cat_name(cat), pts, sample, len(g["rolls"])))

    rows.sort(key=lambda r: -r[0])
    print(f"{len(rows)} distinct optimal first-turn outcomes "
          f"(from 252 rolls), ranked by expected final total:\n")
    print(f"{'rank':>4}  {'box':14s} {'pts':>4}  {'sample dice':17s} "
          f"{'exp final':>9}  {'#rolls':>6}")
    for i, (ev, box, pts, sample, n) in enumerate(rows):
        dice = "".join(str(d) for d in sample)
        print(f"{i:>4}  {box:14s} {pts:>4}  {dice:17s} {ev:>9.2f}  {n:>6}")

    # ── Alternative scope: ALL legal (box, score) placements, not just optimal ──
    all_pos, all_pos_nonzero = set(), set()
    for idx in range(len(ALL_DICE_STATES)):
        row = SCORE_ROWS[idx]
        for c in range(NUM_CATEGORIES):
            s = int(row[c])
            all_pos.add((c, s))
            if s > 0:
                all_pos_nonzero.add((c, s))
    print(f"\nFor comparison — ALL legal (box, score) placements on turn 1:")
    print(f"  including zeros : {len(all_pos)}")
    print(f"  nonzero only    : {len(all_pos_nonzero)}")


if __name__ == "__main__":
    main()
