"""
Aggregate state properties using precomputed one-turn kernels.

This file collects the main forward/backward property computations.

Prerequisites:
    - data/state_properties/level_00 ... level_13 exist
    - data/turn_kernels/level_00 ... level_12 exist

Typical usage:

    python aggregate_properties.py forward-scalars
    python aggregate_properties.py backward-scalars
    python aggregate_properties.py forward-score-dist
    python aggregate_properties.py backward-score-dist
    python aggregate_properties.py backward-box-dist --category FullHouse
    python aggregate_properties.py backward-box-dist --all

The turn kernels contain the compressed end-of-turn distributions:

    category, box_points, reward, next_upper, next_eligible, numerator

so this file never needs to know about within-turn rerolls.
"""

from __future__ import annotations

import argparse
import os

import numpy as np
from tqdm import tqdm

from constants import (
    NUM_CATEGORIES,
    CATEGORY_NAMES,
    UPPER_BONUS_THRESHOLD,
)
from state_properties import STATE_PROPERTIES_DIR, load_shard, save_shard
from turn_kernel import DENOM, load_turn_kernel, row_slice


# ---------------------------------------------------------------------
# Shared constants / names
# ---------------------------------------------------------------------

FULL_MASK = (1 << NUM_CATEGORIES) - 1

REACH_PROB = "reach_prob"
SCORE_SUM_BEFORE = "score_sum_before"
EXPECTED_SCORE_BEFORE = "expected_score_before"

EXPECTED_SCORE_AFTER_CHECK = "expected_score_after_check"
P_TOP_BONUS_AFTER = "p_top_bonus_after"

SCORE_DIST_BEFORE = "score_dist_before"
SCORE_DIST_AFTER = "score_dist_after"

MAX_SCORE = 1575
N_SCORE_BINS = MAX_SCORE + 1

MAX_BOX_POINTS = 50
N_BOX_BINS = MAX_BOX_POINTS + 1


def box_after_name(category: int) -> str:
    return f"box_score_dist_after_{category:02d}"


def category_from_arg(arg: str) -> int:
    try:
        c = int(arg)
    except ValueError:
        if arg not in CATEGORY_NAMES:
            raise ValueError(
                f"Unknown category {arg!r}. Use 0..12 or one of {CATEGORY_NAMES}."
            )
        c = CATEGORY_NAMES.index(arg)

    if not 0 <= c < NUM_CATEGORIES:
        raise ValueError(f"Category must be in 0..{NUM_CATEGORIES - 1}; got {c}")

    return c


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


def load_level_metadata(level: int) -> dict[int, dict[str, np.ndarray]]:
    """Load upper/eligible row metadata for all masks in a level."""
    out = {}

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)

        out[mask] = {
            "upper_total": upper,
            "yahtzee_eligible": eligible,
            "row_for": make_row_lookup(upper, eligible),
            "n_rows": np.array(len(upper), dtype=np.int64),
        }

    return out


def conditional_expectation(score_sum: np.ndarray, reach: np.ndarray) -> np.ndarray:
    out = np.full_like(score_sum, np.nan, dtype=np.float64)
    np.divide(score_sum, reach, out=out, where=(reach > 0))
    return out


# ---------------------------------------------------------------------
# Forward scalar aggregates
# ---------------------------------------------------------------------

def seed_forward_scalars() -> None:
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


def load_forward_scalars(level: int, mask: int) -> tuple[np.ndarray, np.ndarray]:
    with load_shard(level, mask) as shard:
        if REACH_PROB not in shard.files or SCORE_SUM_BEFORE not in shard.files:
            raise KeyError(
                f"Missing forward scalar arrays in level={level}, mask={mask:013b}."
            )

        reach = shard[REACH_PROB].astype(np.float64)
        score_sum = shard[SCORE_SUM_BEFORE].astype(np.float64)

    return reach, score_sum


def save_forward_scalars(level: int, mask: int, reach: np.ndarray, score_sum: np.ndarray) -> None:
    expected = conditional_expectation(score_sum, reach)

    save_shard(
        level,
        mask,
        merge=True,
        reach_prob=reach.astype(np.float64),
        score_sum_before=score_sum.astype(np.float64),
        expected_score_before=expected.astype(np.float64),
    )


def propagate_forward_scalar_level(level: int) -> None:
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

    for mask in tqdm(current_masks, desc=f"forward scalars L{level:02d}"):
        reach, score_sum = load_forward_scalars(level, mask)

        with load_turn_kernel(level, mask) as kernel:
            denom = float(int(kernel["denom"])) if "denom" in kernel.files else float(DENOM)

            category_all = kernel["category"]
            reward_all = kernel["reward"]
            next_upper_all = kernel["next_upper"]
            next_eligible_all = kernel["next_eligible"]
            numerator_all = kernel["numerator"]

            for row in range(len(reach)):
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
        save_forward_scalars(level + 1, mask, next_reach[mask], next_score_sum[mask])


def run_forward_scalars() -> None:
    seed_forward_scalars()

    for level in range(NUM_CATEGORIES):
        propagate_forward_scalar_level(level)

    print("Done. Wrote reach_prob, score_sum_before, expected_score_before.")


# ---------------------------------------------------------------------
# Backward scalar aggregates
# ---------------------------------------------------------------------

def seed_backward_scalars() -> None:
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


def load_backward_scalar_next_tables(level: int) -> dict[int, dict[str, np.ndarray]]:
    out = {}

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)

            if EXPECTED_SCORE_AFTER_CHECK not in shard.files:
                raise KeyError(
                    f"Missing {EXPECTED_SCORE_AFTER_CHECK} in level={level}, mask={mask:013b}"
                )
            if P_TOP_BONUS_AFTER not in shard.files:
                raise KeyError(
                    f"Missing {P_TOP_BONUS_AFTER} in level={level}, mask={mask:013b}"
                )

            expected_after = shard[EXPECTED_SCORE_AFTER_CHECK].astype(np.float64)
            p_top_bonus = shard[P_TOP_BONUS_AFTER].astype(np.float64)

        out[mask] = {
            "row_for": make_row_lookup(upper, eligible),
            EXPECTED_SCORE_AFTER_CHECK: expected_after,
            P_TOP_BONUS_AFTER: p_top_bonus,
        }

    return out


def compute_backward_scalar_level(level: int) -> None:
    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}")

    next_tables = load_backward_scalar_next_tables(level + 1)

    for mask in tqdm(masks, desc=f"backward scalars L{level:02d}"):
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


def run_backward_scalars() -> None:
    seed_backward_scalars()

    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_backward_scalar_level(level)

    print("Done. Wrote expected_score_after_check, p_top_bonus_after.")


# ---------------------------------------------------------------------
# Forward score distributions
# ---------------------------------------------------------------------

def seed_forward_score_dist() -> None:
    with load_shard(0, 0) as shard:
        n_rows = int(shard["upper_total"].shape[0])
        upper = shard["upper_total"]
        eligible = shard["yahtzee_eligible"]

    dist = np.zeros((n_rows, N_SCORE_BINS), dtype=np.float32)

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


def load_forward_score_dist(level: int, mask: int) -> tuple[np.ndarray, np.ndarray]:
    with load_shard(level, mask) as shard:
        if SCORE_DIST_BEFORE not in shard.files:
            raise KeyError(
                f"Missing {SCORE_DIST_BEFORE} in level={level}, mask={mask:013b}."
            )
        if REACH_PROB not in shard.files:
            raise KeyError(
                f"Missing {REACH_PROB} in level={level}, mask={mask:013b}. "
                "Run forward-scalars first."
            )

        dist = shard[SCORE_DIST_BEFORE].astype(np.float32)
        reach = shard[REACH_PROB].astype(np.float64)

    return dist, reach


def propagate_forward_score_dist_level(level: int) -> None:
    current_masks = list_masks_for_level(level)
    next_meta = load_level_metadata(level + 1)

    if not current_masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}")
    if not next_meta:
        raise FileNotFoundError(f"No state_properties shards found for level {level + 1}")

    next_dist = {
        mask: np.zeros((int(meta["n_rows"]), N_SCORE_BINS), dtype=np.float32)
        for mask, meta in next_meta.items()
    }

    for mask in tqdm(current_masks, desc=f"score dist before L{level:02d}"):
        current_dist, reach = load_forward_score_dist(level, mask)

        with load_turn_kernel(level, mask) as kernel:
            denom = float(int(kernel["denom"])) if "denom" in kernel.files else float(DENOM)

            category_all = kernel["category"]
            reward_all = kernel["reward"]
            next_upper_all = kernel["next_upper"]
            next_eligible_all = kernel["next_eligible"]
            numerator_all = kernel["numerator"]

            for row in range(current_dist.shape[0]):
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

                    if r == 0:
                        next_dist[next_mask][next_row] += prob[i] * src
                    else:
                        next_dist[next_mask][next_row, r:] += prob[i] * src[: N_SCORE_BINS - r]

    for mask in sorted(next_meta):
        save_shard(
            level + 1,
            mask,
            merge=True,
            score_dist_before=next_dist[mask],
        )


def run_forward_score_dist() -> None:
    seed_forward_score_dist()

    for level in range(NUM_CATEGORIES):
        propagate_forward_score_dist_level(level)

    print("Done. Wrote score_dist_before.")


# ---------------------------------------------------------------------
# Backward score distributions
# ---------------------------------------------------------------------

def seed_backward_score_dist() -> None:
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

        dist = np.zeros((n_rows, N_SCORE_BINS), dtype=np.float32)
        dist[:, 0] = 1.0

        save_shard(
            level,
            mask,
            merge=True,
            score_dist_after=dist,
        )


def load_backward_score_next_tables(level: int) -> dict[int, dict[str, np.ndarray]]:
    out = {}

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)

            if SCORE_DIST_AFTER not in shard.files:
                raise KeyError(
                    f"Missing {SCORE_DIST_AFTER} in level={level}, mask={mask:013b}"
                )

            dist = shard[SCORE_DIST_AFTER].astype(np.float32)

        out[mask] = {
            "row_for": make_row_lookup(upper, eligible),
            SCORE_DIST_AFTER: dist,
        }

    return out


def compute_backward_score_dist_level(level: int) -> None:
    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}")

    next_tables = load_backward_score_next_tables(level + 1)

    for mask in tqdm(masks, desc=f"score dist after L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])

        out = np.zeros((n_rows, N_SCORE_BINS), dtype=np.float32)

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

                    if r == 0:
                        row_out += prob[i] * succ_dist
                    else:
                        row_out[r:] += prob[i] * succ_dist[: N_SCORE_BINS - r]

        save_shard(
            level,
            mask,
            merge=True,
            score_dist_after=out.astype(np.float32),
        )


def run_backward_score_dist() -> None:
    seed_backward_score_dist()

    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_backward_score_dist_level(level)

    print("Done. Wrote score_dist_after.")


# ---------------------------------------------------------------------
# Backward per-box distributions
# ---------------------------------------------------------------------

def seed_backward_box_dist(category: int) -> None:
    level = NUM_CATEGORIES
    name = box_after_name(category)

    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(
            f"No state_properties shards found for level {level}. "
            "Run build_terminal_shards.py first."
        )

    for mask in masks:
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])

        dist = np.zeros((n_rows, N_BOX_BINS), dtype=np.float32)

        save_shard(
            level,
            mask,
            merge=True,
            **{name: dist},
        )


def load_backward_box_next_tables(level: int, category: int) -> dict[int, dict[str, np.ndarray]]:
    name = box_after_name(category)
    out = {}

    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)

            if name not in shard.files:
                raise KeyError(
                    f"Missing {name} in level={level}, mask={mask:013b}. "
                    "Run backward-box-dist from terminal level backward."
                )

            dist = shard[name].astype(np.float32)

        out[mask] = {
            "row_for": make_row_lookup(upper, eligible),
            name: dist,
        }

    return out


def compute_backward_box_dist_level(level: int, category: int) -> None:
    name = box_after_name(category)
    masks = list_masks_for_level(level)

    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}")

    next_tables = load_backward_box_next_tables(level + 1, category)

    for mask in tqdm(masks, desc=f"{name} L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])

        out = np.zeros((n_rows, N_BOX_BINS), dtype=np.float32)

        # Convention: if target category is already filled, future box-score
        # distribution is all zeros.
        if mask & (1 << category):
            save_shard(level, mask, merge=True, **{name: out})
            continue

        with load_turn_kernel(level, mask) as kernel:
            denom = float(int(kernel["denom"])) if "denom" in kernel.files else float(DENOM)

            category_all = kernel["category"]
            box_points_all = kernel["box_points"]
            next_upper_all = kernel["next_upper"]
            next_eligible_all = kernel["next_eligible"]
            numerator_all = kernel["numerator"]

            for row in range(n_rows):
                s = row_slice(kernel, row)

                outcome_cat = category_all[s].astype(np.int64)
                box_points = box_points_all[s].astype(np.int64)
                next_upper = next_upper_all[s].astype(np.int64)
                next_eligible = next_eligible_all[s].astype(np.int64)
                prob = numerator_all[s].astype(np.float64) / denom

                row_out = out[row]

                for i in range(len(prob)):
                    p = float(prob[i])
                    c = int(outcome_cat[i])

                    if c == category:
                        points = int(box_points[i])
                        if not 0 <= points <= MAX_BOX_POINTS:
                            raise ValueError(
                                f"box_points={points} outside 0..{MAX_BOX_POINTS}"
                            )
                        row_out[points] += p
                    else:
                        next_mask = mask | (1 << c)
                        tables = next_tables[next_mask]

                        next_row = int(
                            tables["row_for"][int(next_upper[i]), int(next_eligible[i])]
                        )
                        if next_row < 0:
                            raise KeyError(
                                f"Missing successor row: level={level + 1}, "
                                f"mask={next_mask:013b}, upper={int(next_upper[i])}, "
                                f"eligible={bool(next_eligible[i])}"
                            )

                        row_out += p * tables[name][next_row]

        save_shard(
            level,
            mask,
            merge=True,
            **{name: out.astype(np.float32)},
        )


def run_backward_box_dist(category: int) -> None:
    print(f"Computing after-distribution for {category}: {CATEGORY_NAMES[category]}")
    seed_backward_box_dist(category)

    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_backward_box_dist_level(level, category)

    print(f"Done. Wrote {box_after_name(category)}.")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("forward-scalars")
    sub.add_parser("backward-scalars")
    sub.add_parser("forward-score-dist")
    sub.add_parser("backward-score-dist")

    p_box = sub.add_parser("backward-box-dist")
    p_box.add_argument("--category", type=str, default=None)
    p_box.add_argument("--all", action="store_true")

    args = parser.parse_args()

    if args.command == "forward-scalars":
        run_forward_scalars()
    elif args.command == "backward-scalars":
        run_backward_scalars()
    elif args.command == "forward-score-dist":
        run_forward_score_dist()
    elif args.command == "backward-score-dist":
        run_backward_score_dist()
    elif args.command == "backward-box-dist":
        if args.all:
            categories = list(range(NUM_CATEGORIES))
        elif args.category is not None:
            categories = [category_from_arg(args.category)]
        else:
            raise SystemExit("Pass --category <0..12/name> or --all.")

        for category in categories:
            run_backward_box_dist(category)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()