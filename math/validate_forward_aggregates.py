"""
Validate forward scalar aggregates.

Run from project root:

    python validate_forward_aggregates.py
"""

from __future__ import annotations

import os

import numpy as np

from constants import NUM_CATEGORIES
from state_properties import STATE_PROPERTIES_DIR, load_shard


REACH_PROB = "reach_prob"
SCORE_SUM_BEFORE = "score_sum_before"
EXPECTED_SCORE_BEFORE = "expected_score_before"


def list_masks_for_level(level: int) -> list[int]:
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []

    masks = []
    for filename in os.listdir(level_dir):
        if filename.endswith(".npz"):
            masks.append(int(filename[:-4], 2))

    return sorted(masks)


def level_totals(level: int) -> tuple[float, float]:
    total_reach = 0.0
    total_score_sum = 0.0

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            total_reach += float(np.sum(shard[REACH_PROB]))
            total_score_sum += float(np.sum(shard[SCORE_SUM_BEFORE]))

    return total_reach, total_score_sum


def main() -> None:
    with load_shard(0, 0) as shard:
        initial_v = float(shard["V"][0])

    print(f"initial V: {initial_v:.12f}")
    print()

    for level in range(NUM_CATEGORIES + 1):
        reach, score_sum = level_totals(level)
        print(
            f"level {level:2d}: "
            f"reach mass={reach:.12f}, "
            f"unconditional score before={score_sum:.12f}"
        )

    terminal_reach, terminal_score_sum = level_totals(NUM_CATEGORIES)

    print()
    print(f"terminal reach mass:       {terminal_reach:.12f}")
    print(f"terminal expected score:   {terminal_score_sum:.12f}")
    print(f"initial V:                 {initial_v:.12f}")
    print(f"difference:                {terminal_score_sum - initial_v:.12f}")

    if abs(terminal_reach - 1.0) > 1e-8:
        raise SystemExit("Terminal reach mass is not close to 1.")

    if abs(terminal_score_sum - initial_v) > 1e-3:
        raise SystemExit("Terminal expected score does not match initial V.")

    print("validation passed")


if __name__ == "__main__":
    main()