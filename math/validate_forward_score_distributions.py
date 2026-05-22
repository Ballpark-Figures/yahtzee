"""
Validate forward score distributions.

Checks:

    sum_x score_dist_before[state, x] == reach_prob[state]

and level totals:

    sum_state,x score_dist_before[level, state, x] == 1
    sum_state,x x * score_dist_before[level, state, x]
        == unconditional score before from forward_aggregates.py

Run from project root:

    python validate_forward_score_distributions.py
"""

from __future__ import annotations

import os

import numpy as np

from constants import NUM_CATEGORIES
from state_properties import STATE_PROPERTIES_DIR, load_shard


SCORE_DIST_BEFORE = "score_dist_before"
REACH_PROB = "reach_prob"
SCORE_SUM_BEFORE = "score_sum_before"


def list_masks_for_level(level: int) -> list[int]:
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []

    masks = []
    for filename in os.listdir(level_dir):
        if filename.endswith(".npz"):
            masks.append(int(filename[:-4], 2))

    return sorted(masks)


def validate_level(level: int) -> tuple[float, float, float, float]:
    total_mass = 0.0
    total_mean = 0.0
    total_reach = 0.0
    total_score_sum = 0.0
    worst_row_mass_error = 0.0

    scores = None

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            dist = shard[SCORE_DIST_BEFORE].astype(np.float64)
            reach = shard[REACH_PROB].astype(np.float64)
            score_sum = shard[SCORE_SUM_BEFORE].astype(np.float64)

        if scores is None:
            scores = np.arange(dist.shape[1], dtype=np.float64)

        row_mass = dist.sum(axis=1)
        worst_row_mass_error = max(
            worst_row_mass_error,
            float(np.max(np.abs(row_mass - reach))) if len(row_mass) else 0.0,
        )

        total_mass += float(row_mass.sum())
        total_mean += float(dist @ scores).sum()
        total_reach += float(reach.sum())
        total_score_sum += float(score_sum.sum())

    mass_error = total_mass - total_reach
    mean_error = total_mean - total_score_sum
    return total_mass, total_mean, worst_row_mass_error, mass_error, mean_error


def main() -> None:
    worst_row_mass_error = 0.0
    worst_level_mass_error = 0.0
    worst_level_mean_error = 0.0

    for level in range(NUM_CATEGORIES + 1):
        total_mass, total_mean, row_err, mass_err, mean_err = validate_level(level)

        worst_row_mass_error = max(worst_row_mass_error, abs(row_err))
        worst_level_mass_error = max(worst_level_mass_error, abs(mass_err))
        worst_level_mean_error = max(worst_level_mean_error, abs(mean_err))

        print(
            f"level {level:2d}: "
            f"dist mass={total_mass:.12f}, "
            f"dist mean={total_mean:.12f}, "
            f"worst row mass err={row_err:.6g}, "
            f"level mass err={mass_err:.6g}, "
            f"level mean err={mean_err:.6g}"
        )

    print()
    print(f"worst row mass error:    {worst_row_mass_error:.12g}")
    print(f"worst level mass error:  {worst_level_mass_error:.12g}")
    print(f"worst level mean error:  {worst_level_mean_error:.12g}")

    if worst_row_mass_error > 1e-4:
        raise SystemExit("Row mass error too large.")

    if worst_level_mass_error > 1e-4:
        raise SystemExit("Level mass error too large.")

    if worst_level_mean_error > 1e-2:
        raise SystemExit("Level mean error too large.")

    print("validation passed")


if __name__ == "__main__":
    main()