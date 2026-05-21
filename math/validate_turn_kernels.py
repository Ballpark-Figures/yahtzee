"""
Validate generated turn-kernel files.

Run from project root:

    python validate_turn_kernels.py

Useful options:

    python validate_turn_kernels.py --max-states-per-level 100
    python validate_turn_kernels.py --start-level 0 --end-level 12
    python validate_turn_kernels.py --full
"""

from __future__ import annotations

import argparse
import os
import random

import numpy as np
from tqdm import tqdm

from constants import UPPER_BONUS_THRESHOLD
from state_properties import STATE_PROPERTIES_DIR, load_shard
from turn_kernel import DENOM, load_turn_kernel, row_slice


def list_masks_for_level(level: int) -> list[int]:
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []

    masks = []
    for filename in os.listdir(level_dir):
        if filename.endswith(".npz"):
            masks.append(int(filename[:-4], 2))
    return sorted(masks)


def load_v_table(level: int, mask: int) -> np.ndarray:
    with load_shard(level, mask) as shard:
        table = np.zeros((UPPER_BONUS_THRESHOLD + 1, 2), dtype=np.float64)
        table[
            shard["upper_total"],
            shard["yahtzee_eligible"].astype(np.int8),
        ] = shard["V"]
    return table


def validate_row(level: int, mask: int, row: int, next_v_cache: dict[tuple[int, int], np.ndarray]) -> tuple[float, float]:
    """Return (prob_error, value_error) for one row."""
    with load_shard(level, mask) as shard, load_turn_kernel(level, mask) as kernel:
        stored_v = float(shard["V"][row])

        s = row_slice(kernel, row)

        category = kernel["category"][s].astype(np.int64)
        reward = kernel["reward"][s].astype(np.float64)
        next_upper = kernel["next_upper"][s].astype(np.int64)
        next_eligible = kernel["next_eligible"][s].astype(np.int64)
        numerator = kernel["numerator"][s].astype(np.float64)

        prob = numerator / float(DENOM)
        prob_error = abs(float(prob.sum()) - 1.0)

        reconstructed = 0.0
        for i in range(len(prob)):
            next_mask = mask | (1 << int(category[i]))
            key = (level + 1, next_mask)

            if key not in next_v_cache:
                next_v_cache[key] = load_v_table(level + 1, next_mask)

            next_v = next_v_cache[key]
            reconstructed += prob[i] * (
                reward[i] + next_v[int(next_upper[i]), int(next_eligible[i])]
            )

        value_error = reconstructed - stored_v
        return prob_error, value_error


def choose_rows(n_rows: int, max_rows: int | None, rng: random.Random) -> list[int]:
    if max_rows is None or max_rows >= n_rows:
        return list(range(n_rows))
    return sorted(rng.sample(range(n_rows), max_rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-level", type=int, default=0)
    parser.add_argument("--end-level", type=int, default=12)
    parser.add_argument("--max-states-per-level", type=int, default=200)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    max_rows_per_level = None if args.full else args.max_states_per_level

    worst_prob_error = 0.0
    worst_value_error = 0.0
    checked = 0

    next_v_cache: dict[tuple[int, int], np.ndarray] = {}

    for level in range(args.start_level, args.end_level + 1):
        masks = list_masks_for_level(level)
        if not masks:
            print(f"level {level:2d}: no shards")
            continue

        # Sample rows across the whole level, not max_rows per shard.
        candidates = []
        for mask in masks:
            with load_shard(level, mask) as shard:
                n_rows = int(shard["upper_total"].shape[0])
            for row in range(n_rows):
                candidates.append((mask, row))

        chosen = choose_rows(len(candidates), max_rows_per_level, rng)
        selected = [candidates[i] for i in chosen]

        print(f"level {level:2d}: checking {len(selected):,} / {len(candidates):,} states")

        for mask, row in tqdm(selected, desc=f"validate L{level:02d}"):
            prob_error, value_error = validate_row(level, mask, row, next_v_cache)
            checked += 1

            worst_prob_error = max(worst_prob_error, prob_error)
            worst_value_error = max(worst_value_error, abs(value_error))

            if prob_error > 1e-12 or abs(value_error) > 1e-3:
                print()
                print("Large validation error:")
                print(f"  level={level}")
                print(f"  mask={mask:013b}")
                print(f"  row={row}")
                print(f"  prob_error={prob_error}")
                print(f"  value_error={value_error}")
                raise SystemExit(1)

    print()
    print(f"checked states:       {checked:,}")
    print(f"worst prob error:     {worst_prob_error}")
    print(f"worst abs V error:    {worst_value_error}")
    print("validation passed")


if __name__ == "__main__":
    main()