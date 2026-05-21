"""
Basic tests/debugging for turn_kernel.py.

Run from project root:

    python test_turn_kernel.py

The most important check is value reconstruction:

    V(s) == E[immediate_reward + V(successor)]

If that agrees, then the one-turn kernel is matching the already-computed
optimal policy.
"""

from __future__ import annotations

import numpy as np

from constants import UPPER_BONUS_THRESHOLD
from state_properties import load_shard, row_index
from turn_kernel import (
    row_turn_outcomes,
    print_row_turn_outcomes,
    probability_sum,
    expected_immediate_reward,
    next_mask_from_outcome,
)


def load_v_table(level: int, mask: int) -> np.ndarray:
    """Return table[upper_total, eligible_idx] = V for one shard."""
    with load_shard(level, mask) as shard:
        table = np.zeros((UPPER_BONUS_THRESHOLD + 1, 2), dtype=np.float64)
        table[
            shard["upper_total"],
            shard["yahtzee_eligible"].astype(np.int8),
        ] = shard["V"]

    return table


def check_probability_sum(
    *,
    level: int,
    mask: int,
    upper: int,
    eligible: bool,
    min_prob: float = 0.001,
) -> None:
    with load_shard(level, mask) as shard:
        row = row_index(shard, upper, eligible)
        outcomes = row_turn_outcomes(mask, shard, row)

        print_row_turn_outcomes(mask, shard, row, min_prob=min_prob)
        print()
        print("probability sum:", probability_sum(outcomes))
        print("one-turn expected immediate reward:", expected_immediate_reward(outcomes))
        print("stored V:", float(shard["V"][row]))


def check_value_reconstruction(
    *,
    level: int,
    mask: int,
    upper: int,
    eligible: bool,
) -> None:
    """Check V(s) = E[reward + V(succ)] for one state."""
    with load_shard(level, mask) as shard:
        row = row_index(shard, upper, eligible)
        outcomes = row_turn_outcomes(mask, shard, row)
        stored = float(shard["V"][row])

    next_v_cache: dict[int, np.ndarray] = {}
    reconstructed = 0.0

    for o in outcomes:
        next_mask = next_mask_from_outcome(mask, o)

        if next_mask not in next_v_cache:
            next_v_cache[next_mask] = load_v_table(level + 1, next_mask)

        next_v = next_v_cache[next_mask]
        reconstructed += o.prob * (
            o.reward + next_v[o.next_upper, o.next_eligible_idx]
        )

    print("stored V:       ", stored)
    print("reconstructed V:", reconstructed)
    print("difference:     ", reconstructed - stored)


def main() -> None:
    # Initial state.
    level = 0
    mask = 0
    upper = 0
    eligible = False

    print("=== Probability / outcome sanity check ===")
    check_probability_sum(
        level=level,
        mask=mask,
        upper=upper,
        eligible=eligible,
        min_prob=0.001,
    )

    print()
    print("=== Value reconstruction check ===")
    check_value_reconstruction(
        level=level,
        mask=mask,
        upper=upper,
        eligible=eligible,
    )


if __name__ == "__main__":
    main()