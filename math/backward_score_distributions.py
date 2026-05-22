"""
Backward score distributions over generated one-turn kernels.

Computes and writes:

    score_dist_after

into data/state_properties/level_kk/<mask>.npz.

Interpretation:

    score_dist_after[row, x]
        = P(score_future = x | start from this reduced state row)

So each row should sum to 1, and its mean should match V[row].

Run from project root:

    python backward_score_distributions.py

Prerequisites:
    python backward_aggregates.py
    data/turn_kernels/level_00 ... level_12 exist
    data/state_properties/level_13 exists
"""

from __future__ import annotations

import argparse
import os

import numpy as np
from tqdm import tqdm

from constants import NUM_CATEGORIES, UPPER_BONUS_THRESHOLD
from state_properties import STATE_PROPERTIES_DIR, load_shard, save_shard
from turn_kernel import DENOM, load_turn_kernel, row_slice


SCORE_DIST_AFTER = "score_dist_after"

# Official Yahtzee maximum is 1575:
# 375 base max + 12 extra Yahtzee bonuses.
MAX_SCORE = 1575
N_BINS = MAX_SCORE + 1


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
    row_for[
        upper.astype(np.int64),
        eligible.astype(np.int8),
    ] = np.arange(len(upper), dtype=np.int64)
    return row_for


def load_next_level_tables(level: int) -> dict[int, dict[str, np.ndarray]]:
    """Load score_dist_after and row lookup tables for all masks in one level."""
    out = {}

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)

            if SCORE_DIST_AFTER not in shard.files:
                raise KeyError(
                    f"Missing {SCORE_DIST_AFTER} in "
                    f"level={level}, mask={mask:013b}"
                )

            dist = shard[SCORE_DIST_AFTER].astype(np.float32)

        out[mask] = {
            "row_for": make_row_lookup(upper, eligible),
            SCORE_DIST_AFTER: dist,
        }

    return out


def seed_terminal_distribution() -> None:
    """Initialize score_dist_after at terminal level 13."""
    level = NUM_CATEGORIES
    masks = list_masks_for_level(level)

    if not masks:
        raise FileNotFoundError(
            f"No state_properties shards found for level {level}. "
            "Run build_terminal_shards.py first."
        )

    for mask in masks:
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])

        dist = np.zeros((n_rows, N_BINS), dtype=np.float32)
        dist[:, 0] = 1.0

        save_shard(
            level,
            mask,
            merge=True,
            score_dist_after=dist,
        )


def compute_level(level: int) -> None:
    """Compute score_dist_after for one nonterminal level."""
    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}")

    next_tables = load_next_level_tables(level + 1)

    for mask in tqdm(masks, desc=f"score dist after L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])

        out = np.zeros((n_rows, N_BINS), dtype=np.float32)

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
                reward = reward_all[s].astype(np.int64)
                next_upper = next_upper_all[s].astype(np.int64)
                next_eligible = next_eligible_all[s].astype(np.int64)
                prob = numerator_all[s].astype(np.float64) / denom

                row_out = out[row]

                for i in range(len(prob)):
                    r = int(reward[i])
                    if r > MAX_SCORE:
                        raise ValueError(f"Reward {r} exceeds MAX_SCORE={MAX_SCORE}")

                    next_mask = mask | (1 << int(category[i]))
                    tables = next_tables[next_mask]

                    next_row = int(tables["row_for"][int(next_upper[i]), int(next_eligible[i])])
                    if next_row < 0:
                        raise KeyError(
                            f"Missing successor row: level={level + 1}, "
                            f"mask={next_mask:013b}, upper={int(next_upper[i])}, "
                            f"eligible={bool(next_eligible[i])}"
                        )

                    succ_dist = tables[SCORE_DIST_AFTER][next_row]

                    # row_out[x + r] += p * succ_dist[x]
                    if r == 0:
                        row_out += prob[i] * succ_dist
                    else:
                        row_out[r:] += prob[i] * succ_dist[: N_BINS - r]

        for_save = out.astype(np.float32)

        save_shard(
            level,
            mask,
            merge=True,
            score_dist_after=for_save,
        )


def run_backward_score_distributions() -> None:
    seed_terminal_distribution()

    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_level(level)

    print("Done. Wrote score_dist_after.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run_backward_score_distributions()


if __name__ == "__main__":
    main()