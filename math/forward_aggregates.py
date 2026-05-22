"""
Forward scalar aggregates over the generated one-turn kernels.

Computes and writes these arrays into data/state_properties/level_kk/<mask>.npz:

    reach_prob
        P(reach this reduced state under optimal play)

    score_sum_before
        E[score_before * 1{reach this state}]

    expected_score_before
        E[score_before | reach this state]
        NaN for states with reach_prob == 0.

Run from project root:

    python forward_aggregates.py

Prerequisites:
    - data/state_properties/level_00 ... level_13 exist
    - data/turn_kernels/level_00 ... level_12 exist
"""

from __future__ import annotations

import argparse
import os

import numpy as np
from tqdm import tqdm

from constants import NUM_CATEGORIES, UPPER_BONUS_THRESHOLD
from state_properties import STATE_PROPERTIES_DIR, load_shard, save_shard
from turn_kernel import DENOM, load_turn_kernel, row_slice


REACH_PROB = "reach_prob"
SCORE_SUM_BEFORE = "score_sum_before"
EXPECTED_SCORE_BEFORE = "expected_score_before"

FULL_MASK = (1 << NUM_CATEGORIES) - 1


def list_masks_for_level(level: int) -> list[int]:
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []

    masks = []
    for filename in os.listdir(level_dir):
        if filename.endswith(".npz"):
            masks.append(int(filename[:-4], 2))

    return sorted(masks)


def load_level_metadata(level: int) -> dict[int, dict[str, np.ndarray]]:
    """Load upper/eligible rows and row lookup tables for all masks in a level."""
    out = {}

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)

        row_for = np.full((UPPER_BONUS_THRESHOLD + 1, 2), -1, dtype=np.int64)
        row_for[upper, eligible.astype(np.int8)] = np.arange(len(upper), dtype=np.int64)

        out[mask] = {
            "upper_total": upper,
            "yahtzee_eligible": eligible,
            "row_for": row_for,
            "n_rows": np.array(len(upper), dtype=np.int64),
        }

    return out


def conditional_expectation(score_sum: np.ndarray, reach: np.ndarray) -> np.ndarray:
    out = np.full_like(score_sum, np.nan, dtype=np.float64)
    np.divide(score_sum, reach, out=out, where=(reach > 0))
    return out


def seed_initial_state() -> None:
    """Initialize level 0 forward arrays."""
    with load_shard(0, 0) as shard:
        n_rows = int(shard["upper_total"].shape[0])
        upper = shard["upper_total"]
        eligible = shard["yahtzee_eligible"]

    reach = np.zeros(n_rows, dtype=np.float64)
    score_sum = np.zeros(n_rows, dtype=np.float64)

    rows = np.where((upper == 0) & (~eligible))[0]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one initial row; found {len(rows)}")

    reach[int(rows[0])] = 1.0
    expected = conditional_expectation(score_sum, reach)

    save_shard(
        0,
        0,
        merge=True,
        reach_prob=reach,
        score_sum_before=score_sum,
        expected_score_before=expected,
    )


def load_current_forward_arrays(level: int, mask: int) -> tuple[np.ndarray, np.ndarray]:
    with load_shard(level, mask) as shard:
        if REACH_PROB not in shard.files or SCORE_SUM_BEFORE not in shard.files:
            raise KeyError(
                f"Missing forward arrays in level={level}, mask={mask:013b}. "
                "Run from level 0, or make sure the previous level wrote them."
            )

        reach = shard[REACH_PROB].astype(np.float64)
        score_sum = shard[SCORE_SUM_BEFORE].astype(np.float64)

    return reach, score_sum


def save_forward_arrays(level: int, mask: int, reach: np.ndarray, score_sum: np.ndarray) -> None:
    expected = conditional_expectation(score_sum, reach)

    save_shard(
        level,
        mask,
        merge=True,
        reach_prob=reach.astype(np.float64),
        score_sum_before=score_sum.astype(np.float64),
        expected_score_before=expected.astype(np.float64),
    )


def propagate_level(level: int) -> None:
    """Propagate forward arrays from `level` to `level + 1`."""
    current_masks = list_masks_for_level(level)
    next_meta = load_level_metadata(level + 1)

    if not current_masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}")

    if not next_meta:
        raise FileNotFoundError(f"No state_properties shards found for level {level + 1}")

    next_reach = {
        mask: np.zeros(int(meta["n_rows"]), dtype=np.float64)
        for mask, meta in next_meta.items()
    }
    next_score_sum = {
        mask: np.zeros(int(meta["n_rows"]), dtype=np.float64)
        for mask, meta in next_meta.items()
    }

    for mask in tqdm(current_masks, desc=f"forward L{level:02d}"):
        reach, score_sum = load_current_forward_arrays(level, mask)

        with load_turn_kernel(level, mask) as kernel:
            denom = float(int(kernel["denom"])) if "denom" in kernel.files else float(DENOM)

            category_all = kernel["category"]
            reward_all = kernel["reward"]
            next_upper_all = kernel["next_upper"]
            next_eligible_all = kernel["next_eligible"]
            numerator_all = kernel["numerator"]

            n_rows = len(reach)
            for row in range(n_rows):
                row_reach = reach[row]

                if row_reach == 0:
                    continue

                row_score_sum = score_sum[row]
                s = row_slice(kernel, row)

                category = category_all[s].astype(np.int64)
                reward = reward_all[s].astype(np.float64)
                next_upper = next_upper_all[s].astype(np.int64)
                next_eligible = next_eligible_all[s].astype(np.int64)
                prob = numerator_all[s].astype(np.float64) / denom

                for i in range(len(prob)):
                    next_mask = mask | (1 << int(category[i]))
                    meta = next_meta[next_mask]
                    next_row = int(meta["row_for"][int(next_upper[i]), int(next_eligible[i])])

                    if next_row < 0:
                        raise KeyError(
                            f"Missing successor row: level={level + 1}, "
                            f"mask={next_mask:013b}, upper={int(next_upper[i])}, "
                            f"eligible={bool(next_eligible[i])}"
                        )

                    p = float(prob[i])
                    r = float(reward[i])

                    next_reach[next_mask][next_row] += row_reach * p
                    next_score_sum[next_mask][next_row] += p * (row_score_sum + row_reach * r)

    for mask in sorted(next_meta):
        save_forward_arrays(level + 1, mask, next_reach[mask], next_score_sum[mask])


def run_forward_scalar_aggregates() -> None:
    seed_initial_state()

    for level in range(NUM_CATEGORIES):
        propagate_level(level)

    print("Done. Wrote reach_prob, score_sum_before, expected_score_before.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run_forward_scalar_aggregates()


if __name__ == "__main__":
    main()