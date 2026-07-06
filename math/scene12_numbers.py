"""Scene 12 (two-player) — provenance for every on-screen number.

Beat a: an empty card starts at the whole-game expected score V(empty)=254.6.
Then 12 points are committed to a single box on turn 1, and the "expected total
score" updates to  12 + V(resulting reduced state).  The scene shows three of
these (3 box / 4-kind / 6 box) for a clean good -> pretty bad -> really bad
escalation; chance and 3-kind are computed here too as the candidates that were
weighed when picking those three.

Beat c: the "beat by one simplified point => 97% they also won" figure is the
solver's reduced-point matchup:
    win_prob_given_reduced_point_diff(df, 1)
    = P(A actual score > B actual score | A_reduced - B_reduced = 1),
both players drawing independently from the point-max final-score distribution.

Run from math/ with the ROOT venv (needs pandas/numpy):
    ../.venv/bin/python scene12_numbers.py

Everything READS the solved policy / stored final-outcome distribution; nothing
re-derives strategy.
"""
import numpy as np

from constants import *  # THREES, SIXES, CHANCE, NUM_CATEGORIES, ...
from reduced_game_state import ReducedGameState
from state_explorer import (
    state_value,
    load_reduced_point_df,
    reduced_point_matchup_table,
    reduced_point_marginal,
    win_prob_given_reduced_point_diff,
)


def committed_total(open_cat, points, upper_total):
    """Expected FINAL total after scoring `points` into `open_cat` on turn 1:
    the committed points plus V of the resulting level-1 reduced state."""
    st = ReducedGameState(
        filled_mask=(1 << open_cat),
        upper_total=upper_total,
        yahtzee_eligible=False,
    )
    v = state_value(st)
    return points + v, v


def main():
    empty = ReducedGameState(filled_mask=0, upper_total=0, yahtzee_eligible=False)
    v_empty = state_value(empty)
    print(f"V(empty)  whole-game expected score = {v_empty:.4f}\n")

    print("Beat a — expected TOTAL after committing 12 to a box on turn 1:")
    for label, cat, upper in [
        ("12 in 3 box (four 3s)", THREES, 12),
        ("12 in chance (sum 12)", CHANCE, 0),
        ("12 in 3-kind box (sum 12)", THREE_KIND, 0),
        ("12 in 4-kind box (sum 12)", FOUR_KIND, 0),
        ("12 in 6 box (two 6s)", SIXES, 12),
    ]:
        total, v = committed_total(cat, 12, upper)
        print(f"  {label:24s}  12 + V={v:8.4f}  ->  total = {total:8.4f}  "
              f"(delta vs 254.6 = {total - v_empty:+.4f})")

    print("\nBeat c — reduced-point (simplified 4/2/1) matchup:")
    df = load_reduced_point_df()
    table = reduced_point_matchup_table(df)
    for k in (1, 2, 3):
        p = win_prob_given_reduced_point_diff(df, k, matchup_table=table)
        print(f"  P(win real game | ahead by {k} simplified pt) = {p:.4%}")

    marg = reduced_point_marginal(df)
    print("\n  reduced-point marginal (P of each simplified total):")
    for _, r in marg.iterrows():
        print(f"    {int(r['reduced_points']):2d} pts : {r['p_reduced_points']:.4%}")


if __name__ == "__main__":
    main()
