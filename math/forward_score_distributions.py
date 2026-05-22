"""
Forward score distributions over generated one-turn kernels.

Computes and writes:

    score_dist_before

into data/state_properties/level_kk/<mask>.npz.

Interpretation:

    score_dist_before[row, x]
        = P(reach this reduced state row and score_before = x)

So the row sum should equal reach_prob[row].

Run from project root:

    python forward_score_distributions.py

Prerequisites:
    python forward_aggregates.py
    data/turn_kernels/level_00 ... level_12 exist
"""

from __future__ import annotations

import argparse
import os

import numpy as np
from tqdm import tqdm

from constants import NUM_CATEGORIES, UPPER_BONUS_THRESHOLD
from state_properties import STATE_PROPERTIES_DIR, load_shard, save_shard
from turn_kernel import DENOM, load_turn_kernel, row_slice


SCORE_DIST_BEFORE = "score_dist_before"
REACH_PROB = "reach_prob"

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


def load_level_metadata(level: int) -> dict[int, dict[str, np.ndarray]]:
    """Load row lookup tables for all masks in a level."""
    out = {}

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)

        row_for = np.full((UPPER_BONUS_THRESHOLD + 1, 2), -1, dtype=np.int64)
        row_for[upper, eligible.astype(np.int8)] = np.arange(len(upper), dtype=np.int64)

        out[mask] = {
            "row_for": row_for,
            "n_rows": np.array(len(upper), dtype=np.int64),
        }

    return out


def seed_initial_distribution() -> None:
    """Initialize score_dist_before at level 0."""
    with load_shard(0, 0) as shard:
        n_rows = int(shard["upper_total"].shape[0])
        upper = shard["upper_total"]
        eligible = shard["yahtzee_eligible"]

    dist = np.zeros((n_rows, N_BINS), dtype=np.float32)

    rows = np.where((upper == 0) & (~eligible))[0]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one initial row; found {len(rows)}")

    dist[int(rows[0]), 0] = 1.0

    save_shard(
        0,
        0,
        merge=True,
        score_dist_before=dist,
    )


def load_current_distribution(level: int, mask: int) -> tuple[np.ndarray, np.ndarray]:
    with load_shard(level, mask) as shard:
        if SCORE_DIST_BEFORE not in shard.files:
            raise KeyError(
                f"Missing {SCORE_DIST_BEFORE} in level={level}, mask={mask:013b}. "
                "Run from level 0."
            )

        if REACH_PROB not in shard.files:
            raise KeyError(
                f"Missing {REACH_PROB} in level={level}, mask={mask:013b}. "
                "Run forward_aggregates.py first."
            )

        dist = shard[SCORE_DIST_BEFORE].astype(np.float32)
        reach = shard[REACH_PROB].astype(np.float64)

    return dist, reach


def propagate_level(level: int) -> None:
    """Propagate score_dist_before from `level` to `level + 1`."""
    current_masks = list_masks_for_level(level)
    next_meta = load_level_metadata(level + 1)

    if not current_masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}")

    if not next_meta:
        raise FileNotFoundError(f"No state_properties shards found for level {level + 1}")

    next_dist = {
        mask: np.zeros((int(meta["n_rows"]), N_BINS), dtype=np.float32)
        for mask, meta in next_meta.items()
    }

    for mask in tqdm(current_masks, desc=f"score dist before L{level:02d}"):
        current_dist, reach = load_current_distribution(level, mask)

        with load_turn_kernel(level, mask) as kernel:
            denom = float(int(kernel["denom"])) if "denom" in kernel.files else float(DENOM)

            category_all = kernel["category"]
            reward_all = kernel["reward"]
            next_upper_all = kernel["next_upper"]
            next_eligible_all = kernel["next_eligible"]
            numerator_all = kernel["numerator"]

            n_rows = current_dist.shape[0]

            for row in range(n_rows):
                if reach[row] == 0:
                    continue

                src = current_dist[row]
                if not np.any(src):
                    continue

                s = row_slice(kernel, row)

                category = category_all[s].astype(np.int64)
                reward = reward_all[s].astype(np.int64)
                next_upper = next_upper_all[s].astype(np.int64)
                next_eligible = next_eligible_all[s].astype(np.int64)
                prob = numerator_all[s].astype(np.float64) / denom

                for i in range(len(prob)):
                    r = int(reward[i])
                    if r > MAX_SCORE:
                        raise ValueError(f"Reward {r} exceeds MAX_SCORE={MAX_SCORE}")

                    next_mask = mask | (1 << int(category[i]))
                    meta = next_meta[next_mask]
                    next_row = int(meta["row_for"][int(next_upper[i]), int(next_eligible[i])])

                    if next_row < 0:
                        raise KeyError(
                            f"Missing successor row: level={level + 1}, "
                            f"mask={next_mask:013b}, upper={int(next_upper[i])}, "
                            f"eligible={bool(next_eligible[i])}"
                        )

                    # Shift by immediate reward r:
                    # dest[x + r] += p * src[x]
                    if r == 0:
                        next_dist[next_mask][next_row] += prob[i] * src
                    else:
                        next_dist[next_mask][next_row, r:] += prob[i] * src[: N_BINS - r]

    for mask in sorted(next_meta):
        save_shard(
            level + 1,
            mask,
            merge=True,
            score_dist_before=next_dist[mask],
        )


def run_forward_score_distributions() -> None:
    seed_initial_distribution()

    for level in range(NUM_CATEGORIES):
        propagate_level(level)

    print("Done. Wrote score_dist_before.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run_forward_score_distributions()


if __name__ == "__main__":
    main()