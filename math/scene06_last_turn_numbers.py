"""Scene 06 (last turn) — provenance for every on-screen number.

Each box is treated as the ONLY unfilled box on the last turn: all 12 other
boxes filled, upper_total=35 (so the 63 bonus is unreachable from a single box),
yahtzee_eligible=False (no Yahtzee bonus). That isolates each box's own
probability / EV, which is exactly what the scene shows.

Run from math/ with the ROOT venv (needs pandas/numpy):
    ../.venv/bin/python scene06_last_turn_numbers.py

Everything here READS the solved policy in math/data/state_properties/level_12/;
nothing re-derives strategy. The only non-standard query is p_success_from_roll,
which forward-evaluates the solver's STORED optimal keeps to a success
probability (used for the '3 ones vs 2 sixes' 4-kind comparison).
"""
import numpy as np

from constants import *
from reduced_game_state import ReducedGameState
from state_explorer import (mask_from_categories, box_distribution,
                            distribution_stats, box_distribution_table,
                            get_state_row, keep_to_values)
from precomputed import REROLL_OUTCOMES, SCORE_ROWS, dice_values_to_idx


def last_turn_state(open_cat, upper_total=35):
    """State with only `open_cat` unfilled (last turn), no bonuses in play."""
    filled = [c for c in range(NUM_CATEGORIES) if c != open_cat]
    return ReducedGameState(filled_mask=mask_from_categories(filled),
                            upper_total=upper_total, yahtzee_eligible=False)


def box_stats(open_cat):
    st = last_turn_state(open_cat)
    dist = box_distribution(st, open_cat, when="after")
    s = distribution_stats(dist)
    return s["mean"], s["p_positive"]


def p_success_from_roll(state, opening_roll, cat, forced_keepA=None):
    """P(box `cat` scores > 0) starting from `opening_roll`, following the
    solver's STORED optimal keep at stage A (or `forced_keepA`, a 6-tuple count
    vector) and stage B. Exact enumeration over the two rerolls — a forward
    replay of the solved policy, not a new strategy."""
    from precomputed import KEEP_IDX
    payload, row = get_state_row(state)
    dA, dB = payload["decisions_A"][row], payload["decisions_B"][row]
    i0 = dice_values_to_idx(opening_roll)
    kA = KEEP_IDX[forced_keepA] if forced_keepA is not None else int(dA[i0])
    fA, nA = REROLL_OUTCOMES[(i0, kA)]
    sA = float(sum(nA))
    p = 0.0
    for iB, nb in zip(fA, nA):
        kB = int(dB[int(iB)])
        fB, nB = REROLL_OUTCOMES[(int(iB), kB)]
        sB = float(sum(nB))
        succ = sum(nc for iC, nc in zip(fB, nB) if SCORE_ROWS[int(iC)][cat] > 0)
        p += (nb / sA) * (succ / sB)
    return p


def points_if_succeed(state, opening_roll, cat, forced_keepA=None):
    """E[box score | score > 0] from `opening_roll` under the stored policy (or a
    forced first keep). Same forward replay as p_success_from_roll, but the
    conditional mean of the score. (= EV / P(success); the 'points if you get it'
    that the zg bars use for their WIDTH.)"""
    from precomputed import KEEP_IDX
    payload, row = get_state_row(state)
    dA, dB = payload["decisions_A"][row], payload["decisions_B"][row]
    i0 = dice_values_to_idx(opening_roll)
    kA = KEEP_IDX[forced_keepA] if forced_keepA is not None else int(dA[i0])
    fA, nA = REROLL_OUTCOMES[(i0, kA)]
    sA = float(sum(nA))
    tot_w = tot_s = 0.0
    for iB, nb in zip(fA, nA):
        kB = int(dB[int(iB)])
        fB, nB = REROLL_OUTCOMES[(int(iB), kB)]
        sB = float(sum(nB))
        for iC, nc in zip(fB, nB):
            sc = SCORE_ROWS[int(iC)][cat]
            if sc > 0:
                w = (nb / sA) * (nc / sB)
                tot_w += w
                tot_s += w * sc
    return tot_s / tot_w if tot_w else 0.0


def report():
    print("== TOP SECTION (Ones..Sixes) — expected COUNT of the target value ==")
    st = last_turn_state(ONES)
    tbl = box_distribution_table(st, ONES, when="after")   # score = points = count*1
    mean, ppos = box_stats(ONES)
    print(f"  mean count = {mean:.4f}   P(>=1) = {ppos*100:.2f}%")
    print("  count distribution:")
    for _, r in tbl.iterrows():
        print(f"    {int(r['score'])} of value: {r['prob']*100:5.2f}%")

    print("\n== BOTTOM SECTION — P(success) and EV (box-only) ==")
    for name, cat in [("Yahtzee", YAHTZEE), ("Full House", FULL_HOUSE),
                      ("Large Straight", LARGE_STRAIGHT),
                      ("Small Straight", SMALL_STRAIGHT), ("Chance", CHANCE),
                      ("Four of a Kind", FOUR_KIND), ("Three of a Kind", THREE_KIND)]:
        mean, ppos = box_stats(cat)
        print(f"  {name:16s} P(success) = {ppos*100:5.2f}%   EV = {mean:6.3f}")

    print("\n== CHANCE per-die teaching values (elementary, shown being derived) ==")
    second = sum(max(v, 3.5) for v in range(1, 7)) / 6            # keep 456, reroll 123
    first  = sum(max(v, second) for v in range(1, 7)) / 6        # keep 56,  reroll 1234
    print(f"  avg single die       = 3.5")
    print(f"  2nd-reroll per die   = {second:.4f}  (=17/4 = 4.25)")
    print(f"  1st-reroll per die   = {first:.4f}  (=14/3 = 4.6667)")
    print(f"  total (5 dice)       = {5*first:.4f}  (=70/3 = 23.333)")

    print("\n== 4-KIND: '3 ones vs 2 sixes' success comparison (V34 blanks) ==")
    fk = last_turn_state(FOUR_KIND)
    p_keep1 = p_success_from_roll(fk, [1, 1, 1, 6, 6], FOUR_KIND,
                                  forced_keepA=(3, 0, 0, 0, 0, 0))   # keep three 1s
    p_keep6 = p_success_from_roll(fk, [1, 1, 1, 6, 6], FOUR_KIND)    # optimal = keep two 6s
    print(f"  keep the 1's (three-of-a-kind): {p_keep1*100:.1f}%")
    print(f"  keep the 6's (two-of-a-kind):   {p_keep6*100:.1f}%")
    # zg bars: full width = points-if-succeed, filled = success% -> filled area = EV
    pts1 = points_if_succeed(fk, [1, 1, 1, 6, 6], FOUR_KIND, forced_keepA=(3, 0, 0, 0, 0, 0))
    pts6 = points_if_succeed(fk, [1, 1, 1, 6, 6], FOUR_KIND)
    print(f"  points-if-succeed keep 1's: {pts1:.1f}  (x {p_keep1*100:.0f}% = {pts1*p_keep1:.1f} EV)")
    print(f"  points-if-succeed keep 6's: {pts6:.1f}  (x {p_keep6*100:.0f}% = {pts6*p_keep6:.1f} EV)")


if __name__ == "__main__":
    report()
