"""Scene 09 (top bonus) numbers, sourced from the solved state_properties shards.

Every value here is the expected top-bonus points from a reduced state under
optimal play = 35 * p_top_bonus_after, read via state_explorer (no new math).

Run from the math/ project dir:  python scene09_top_bonus_numbers.py
"""
from constants import CATEGORY_NAMES
from reduced_game_state import ReducedGameState
from state_explorer import box_distribution_stats


def top_bonus_ev(filled_mask, upper_total):
    state = ReducedGameState(
        filled_mask=filled_mask,
        upper_total=upper_total,
        yahtzee_eligible=False,
    )
    return box_distribution_stats(state, "UpperBonus", when="after")["mean"]


# Turn-0: nothing filled yet.
start_ev = top_bonus_ev(0, 0)
print(f"Turn-0 top-bonus EV (empty card): {start_ev:.2f}\n")

# 6 columns (numbers 1..6) x counts 0..5 dice of that number filled on turn 1.
print(f"{'count':>5} | " + " ".join(f"{n:>7}" for n in range(1, 7)))
print("-" * 60)
for c in range(0, 6):
    cells = []
    for n in range(1, 7):
        box = n - 1                       # Ones..Sixes = category 0..5
        upper = min(n * c, 63)
        cells.append(f"{top_bonus_ev(1 << box, upper):7.2f}")
    print(f"{c:>5} | " + " ".join(cells))

print("\n(rows = # of that number scored on turn 1; columns = the number)")
