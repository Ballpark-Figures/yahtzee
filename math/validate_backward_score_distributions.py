"""
Validate backward score distributions.

Checks:

    sum_x score_dist_after[state, x] == 1

and:

    sum_x x * score_dist_after[state, x] == V[state]

Run from project root:

    python validate_backward_score_distributions.py
"""

from __future__ import annotations

import os

import numpy as np

from constants import NUM_CATEGORIES
from state_properties import STATE_PROPERTIES_DIR, load_shard


SCORE_DIST_AFTER = "score_dist_after"


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
    worst_row_mass_error = 0.0
    worst_row_mean_error = 0.0
    total_rows = 0

    mass_sum = 0.0
    mean_sum = 0.0

    scores = None

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            dist = shard[SCORE_DIST_AFTER].astype(np.float64)
            v = shard["V"].astype(np.float64)

        if scores is None:
            scores = np.arange(dist.shape[1], dtype=np.float64)

        row_mass = dist.sum(axis=1)
        row_mean = dist @ scores

        if len(row_mass):
            worst_row_mass_error = max(
                worst_row_mass_error,
                float(np.max(np.abs(row_mass - 1.0))),
            )
            worst_row_mean_error = max(
                worst_row_mean_error,
                float(np.max(np.abs(row_mean - v))),
            )

        mass_sum += float(row_mass.sum())
        mean_sum += float(row_mean.sum())
        total_rows += len(row_mass)

    avg_mass = mass_sum / total_rows if total_rows else np.nan
    avg_mean = mean_sum / total_rows if total_rows else np.nan
    return worst_row_mass_error, worst_row_mean_error, avg_mass, avg_mean


def main() -> None:
    worst_mass_error = 0.0
    worst_mean_error = 0.0

    initial_mean = None
    initial_mass = None
    initial_v = None

    for level in range(NUM_CATEGORIES + 1):
        row_mass_err, row_mean_err, avg_mass, avg_mean = validate_level(level)

        worst_mass_error = max(worst_mass_error, row_mass_err)
        worst_mean_error = max(worst_mean_error, row_mean_err)

        print(
            f"level {level:2d}: "
            f"avg row mass={avg_mass:.12f}, "
            f"avg row mean={avg_mean:.12f}, "
            f"worst row mass err={row_mass_err:.6g}, "
            f"worst row mean err={row_mean_err:.6g}"
        )

        if level == 0:
            with load_shard(0, 0) as shard:
                dist = shard[SCORE_DIST_AFTER][0].astype(np.float64)
                scores = np.arange(dist.shape[0], dtype=np.float64)
                initial_mass = float(dist.sum())
                initial_mean = float(dist @ scores)
                initial_v = float(shard["V"][0])

    print()
    print(f"initial dist mass:       {initial_mass:.12f}")
    print(f"initial dist mean:       {initial_mean:.12f}")
    print(f"initial V:               {initial_v:.12f}")
    print(f"initial mean - V:        {initial_mean - initial_v:.12f}")
    print()
    print(f"worst row mass error:    {worst_mass_error:.12g}")
    print(f"worst row mean error:    {worst_mean_error:.12g}")

    if worst_mass_error > 1e-4:
        raise SystemExit("Row mass error too large.")

    if worst_mean_error > 1e-2:
        raise SystemExit("Row mean error too large.")

    print("validation passed")


if __name__ == "__main__":
    main()