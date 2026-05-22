"""
Backward scalar aggregates over the generated one-turn kernels.

Computes and writes these arrays into data/state_properties/level_kk/<mask>.npz:

    expected_score_after_check
        Recomputed expected future score from this state using turn kernels.
        This should match V.

    p_top_bonus_after
        Probability of eventually ending with the upper bonus, starting from
        this state under optimal play.

Run from project root:

    python backward_aggregates.py

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


EXPECTED_SCORE_AFTER_CHECK = "expected_score_after_check"
P_TOP_BONUS_AFTER = "p_top_bonus_after"

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


def make_row_lookup(upper: np.ndarray, eligible: np.ndarray) -> np.ndarray:
    row_for = np.full((UPPER_BONUS_THRESHOLD + 1, 2), -1, dtype=np.int64)
    row_for[upper.astype(np.int64), eligible.astype(np.int8)] = np.arange(len(upper), dtype=np.int64)
    return row_for


def load_next_level_tables(level: int) -> dict[int, dict[str, np.ndarray]]:
    """Load backward arrays and row lookup tables for all masks in one level."""
    out = {}

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)

            if EXPECTED_SCORE_AFTER_CHECK not in shard.files:
                raise KeyError(
                    f"Missing {EXPECTED_SCORE_AFTER_CHECK} in "
                    f"level={level}, mask={mask:013b}"
                )
            if P_TOP_BONUS_AFTER not in shard.files:
                raise KeyError(
                    f"Missing {P_TOP_BONUS_AFTER} in "
                    f"level={level}, mask={mask:013b}"
                )

            expected_after = shard[EXPECTED_SCORE_AFTER_CHECK].astype(np.float64)
            p_top_bonus = shard[P_TOP_BONUS_AFTER].astype(np.float64)

        out[mask] = {
            "row_for": make_row_lookup(upper, eligible),
            EXPECTED_SCORE_AFTER_CHECK: expected_after,
            P_TOP_BONUS_AFTER: p_top_bonus,
        }

    return out


def seed_terminal_states() -> None:
    """Initialize level 13 terminal arrays."""
    level = NUM_CATEGORIES
    masks = list_masks_for_level(level)

    if not masks:
        raise FileNotFoundError(
            f"No state_properties shards found for level {level}. "
            "Run build_terminal_shards.py first."
        )

    for mask in masks:
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            n_rows = len(upper)

        expected_after = np.zeros(n_rows, dtype=np.float64)
        p_top_bonus = (upper >= UPPER_BONUS_THRESHOLD).astype(np.float64)

        save_shard(
            level,
            mask,
            merge=True,
            expected_score_after_check=expected_after,
            p_top_bonus_after=p_top_bonus,
        )


def compute_level(level: int) -> None:
    """Compute backward arrays for one nonterminal level."""
    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}")

    next_tables = load_next_level_tables(level + 1)

    for mask in tqdm(masks, desc=f"backward L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])

        expected_after = np.zeros(n_rows, dtype=np.float64)
        p_top_bonus = np.zeros(n_rows, dtype=np.float64)

        with load_turn_kernel(level, mask) as kernel:
            denom = float(int(kernel["denom"])) if "denom" in kernel.files else float(DENOM)

            category_all = kernel["category"]
            reward_all = kernel["reward"]
            next_upper_all = kernel["next_upper"]
            next_eligible_all = kernel["next_eligible"]
            numerator_all = kernel["numerator"]

            for row in range(n_rows):
                s = row_slice(kernel, row)

                category = category_all[s].astype(np.int64)
                reward = reward_all[s].astype(np.float64)
                next_upper = next_upper_all[s].astype(np.int64)
                next_eligible = next_eligible_all[s].astype(np.int64)
                prob = numerator_all[s].astype(np.float64) / denom

                ev = 0.0
                p_bonus = 0.0

                for i in range(len(prob)):
                    next_mask = mask | (1 << int(category[i]))
                    tables = next_tables[next_mask]

                    next_row = int(tables["row_for"][int(next_upper[i]), int(next_eligible[i])])
                    if next_row < 0:
                        raise KeyError(
                            f"Missing successor row: level={level + 1}, "
                            f"mask={next_mask:013b}, upper={int(next_upper[i])}, "
                            f"eligible={bool(next_eligible[i])}"
                        )

                    p = float(prob[i])
                    ev += p * (
                        float(reward[i])
                        + float(tables[EXPECTED_SCORE_AFTER_CHECK][next_row])
                    )
                    p_bonus += p * float(tables[P_TOP_BONUS_AFTER][next_row])

                expected_after[row] = ev
                p_top_bonus[row] = p_bonus

        save_shard(
            level,
            mask,
            merge=True,
            expected_score_after_check=expected_after,
            p_top_bonus_after=p_top_bonus,
        )


def run_backward_scalar_aggregates() -> None:
    seed_terminal_states()

    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_level(level)

    print("Done. Wrote expected_score_after_check and p_top_bonus_after.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run_backward_scalar_aggregates()


if __name__ == "__main__":
    main()