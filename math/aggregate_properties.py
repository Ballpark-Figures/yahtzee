"""
Aggregate state properties using precomputed one-turn kernels.

Prerequisites:
    - data/state_properties/level_00 ... level_13 exist
    - data/turn_kernels/level_00 ... level_12 exist

Typical usage:
    python aggregate_properties.py forward-scalars
    python aggregate_properties.py backward-scalars
    python aggregate_properties.py forward-score-dist
    python aggregate_properties.py backward-score-dist
    python aggregate_properties.py backward-box-dist --all
    python aggregate_properties.py forward-box-dist --all
    python aggregate_properties.py forward-yahtzee-bonus-dist
    python aggregate_properties.py backward-yahtzee-bonus-dist
    python aggregate_properties.py backward-final-outcome-dist
    python aggregate_properties.py reduced-point-dist
    python aggregate_properties.py reduced-point-dist --start-only
    python aggregate_properties.py reduced-point-summary
"""

from __future__ import annotations

import argparse
import os

import numpy as np
from tqdm import tqdm

from constants import (
    NUM_CATEGORIES,
    CATEGORY_NAMES,
    THREE_KIND,
    FOUR_KIND,
    FULL_HOUSE,
    SMALL_STRAIGHT,
    LARGE_STRAIGHT,
    SIXES,
    YAHTZEE,
    YAHTZEE_POINTS,
    UPPER_BONUS_THRESHOLD,
    UPPER_BONUS,
    EXTRA_YAHTZEE_BONUS,
)
from state_properties import STATE_PROPERTIES_DIR, load_shard, save_shard
from turn_kernel import DENOM, load_turn_kernel, row_slice


REACH_PROB = "reach_prob"
SCORE_SUM_BEFORE = "score_sum_before"
EXPECTED_SCORE_BEFORE = "expected_score_before"
EXPECTED_SCORE_AFTER_CHECK = "expected_score_after_check"
P_TOP_BONUS_AFTER = "p_top_bonus_after"
SCORE_DIST_BEFORE = "score_dist_before"
SCORE_DIST_AFTER = "score_dist_after"
YAHTZEE_BONUS_DIST_BEFORE = "yahtzee_bonus_dist_before"
YAHTZEE_BONUS_DIST_AFTER = "yahtzee_bonus_dist_after"

MAX_SCORE = 1575
N_SCORE_BINS = MAX_SCORE + 1
MAX_BOX_POINTS = 50
N_BOX_BINS = MAX_BOX_POINTS + 1
MAX_EXTRA_YAHTZEE_BONUSES = NUM_CATEGORIES - 1
N_YAHTZEE_BONUS_BINS = MAX_EXTRA_YAHTZEE_BONUSES + 1

FINAL_OUTCOME_DIST_DIR = "data/final_outcome_dists"
FINAL_OUTCOME_OFFSETS = "offsets"
FINAL_OUTCOME_KEYS = "keys"
FINAL_OUTCOME_PROBS = "probs"

# Packed final-outcome key layout:
#   bits  0..10: score, including all immediate rewards/bonuses
#   bits 11..14: yahtzee_units
#       0 = Yahtzee box scored 0
#       1 = Yahtzee box scored 50 with no extra +100 bonuses
#       k = Yahtzee box scored 50 with k - 1 extra +100 bonuses
#   bits 15..20: flags listed below
SCORE_BITS = 11
YAHTZEE_UNIT_BITS = 4
SCORE_SHIFT = 0
YAHTZEE_UNIT_SHIFT = SCORE_BITS
FLAGS_SHIFT = SCORE_BITS + YAHTZEE_UNIT_BITS
SCORE_MASK = (1 << SCORE_BITS) - 1
YAHTZEE_UNIT_MASK = (1 << YAHTZEE_UNIT_BITS) - 1

FLAG_LARGE_STRAIGHT = 1 << 0
FLAG_SMALL_STRAIGHT = 1 << 1
FLAG_FULL_HOUSE = 1 << 2
FLAG_FOUR_KIND = 1 << 3
FLAG_THREE_KIND = 1 << 4
FLAG_TOP_BONUS = 1 << 5

REDUCED_POINT_DIST_DIR = "data/reduced_point_dists"
REDUCED_POINT_OFFSETS = "offsets"
REDUCED_POINT_KEYS = "keys"
REDUCED_POINT_PROBS = "probs"
REDUCED_POINT_SHIFT = SCORE_BITS
REDUCED_POINT_MASK = (1 << (32 - REDUCED_POINT_SHIFT)) - 1

REDUCED_POINTS_EXTRA_YAHTZEE_BONUS = 4
REDUCED_POINTS_YAHTZEE = 2
REDUCED_POINTS_LARGE_STRAIGHT = 2
REDUCED_POINTS_TOP_BONUS = 2
REDUCED_POINTS_SMALL_STRAIGHT = 1
REDUCED_POINTS_FULL_HOUSE = 1
REDUCED_POINTS_THREE_KIND = 1
REDUCED_POINTS_FOUR_KIND = 1


def box_after_name(category: int) -> str:
    return f"box_score_dist_after_{category:02d}"


def box_before_name(category: int) -> str:
    return f"box_score_dist_before_{category:02d}"


def category_from_arg(arg: str) -> int:
    try:
        c = int(arg)
    except ValueError:
        if arg not in CATEGORY_NAMES:
            raise ValueError(f"Unknown category {arg!r}. Use 0..12 or one of {CATEGORY_NAMES}.")
        c = CATEGORY_NAMES.index(arg)
    if not 0 <= c < NUM_CATEGORIES:
        raise ValueError(f"Category must be in 0..{NUM_CATEGORIES - 1}; got {c}")
    return c


def list_masks_for_level(level: int) -> list[int]:
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []
    return sorted(int(filename[:-4], 2) for filename in os.listdir(level_dir) if filename.endswith(".npz"))


def make_row_lookup(upper: np.ndarray, eligible: np.ndarray) -> np.ndarray:
    row_for = np.full((UPPER_BONUS_THRESHOLD + 1, 2), -1, dtype=np.int64)
    row_for[upper.astype(np.int64), eligible.astype(np.int8)] = np.arange(len(upper), dtype=np.int64)
    return row_for


def load_level_metadata(level: int) -> dict[int, dict[str, np.ndarray]]:
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


def kernel_prob(kernel) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    denom = float(int(kernel["denom"])) if "denom" in kernel.files else float(DENOM)
    return (
        denom,
        kernel["category"],
        kernel["box_points"],
        kernel["reward"],
        kernel["next_upper"],
        kernel["next_eligible"],
        kernel["numerator"],
    )


def extra_yahtzee_bonus_count_from_outcome(*, upper: int, category: int, box_points: int, reward: int) -> int:
    """Infer whether an outcome earned one +100 extra Yahtzee bonus."""
    upper_bonus = 0
    if category <= SIXES and upper < UPPER_BONUS_THRESHOLD and upper + box_points >= UPPER_BONUS_THRESHOLD:
        upper_bonus = UPPER_BONUS
    extra = int(reward) - int(box_points) - upper_bonus
    if extra == 0:
        return 0
    if extra == EXTRA_YAHTZEE_BONUS:
        return 1
    raise ValueError(
        f"Unexpected inferred extra Yahtzee bonus {extra}: upper={upper}, "
        f"category={category}, box_points={box_points}, reward={reward}"
    )


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
    save_shard(0, 0, merge=True, reach_prob=reach, score_sum_before=score_sum,
               expected_score_before=conditional_expectation(score_sum, reach))


def load_forward_scalars(level: int, mask: int) -> tuple[np.ndarray, np.ndarray]:
    with load_shard(level, mask) as shard:
        return shard[REACH_PROB].astype(np.float64), shard[SCORE_SUM_BEFORE].astype(np.float64)


def save_forward_scalars(level: int, mask: int, reach: np.ndarray, score_sum: np.ndarray) -> None:
    save_shard(level, mask, merge=True, reach_prob=reach.astype(np.float64),
               score_sum_before=score_sum.astype(np.float64),
               expected_score_before=conditional_expectation(score_sum, reach).astype(np.float64))


def propagate_forward_scalar_level(level: int) -> None:
    current_masks = list_masks_for_level(level)
    next_meta = load_level_metadata(level + 1)
    next_reach = {m: np.zeros(int(meta["n_rows"]), dtype=np.float64) for m, meta in next_meta.items()}
    next_score_sum = {m: np.zeros(int(meta["n_rows"]), dtype=np.float64) for m, meta in next_meta.items()}

    for mask in tqdm(current_masks, desc=f"forward scalars L{level:02d}"):
        reach, score_sum = load_forward_scalars(level, mask)
        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, _, reward_all, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)
            for row in range(len(reach)):
                row_reach = float(reach[row])
                if row_reach == 0:
                    continue
                s = row_slice(kernel, row)
                for cat, reward, nu, ne, num in zip(category_all[s], reward_all[s], next_upper_all[s], next_eligible_all[s], numerator_all[s]):
                    p = float(num) / denom
                    next_mask = mask | (1 << int(cat))
                    next_row = int(next_meta[next_mask]["row_for"][int(nu), int(ne)])
                    next_reach[next_mask][next_row] += row_reach * p
                    next_score_sum[next_mask][next_row] += p * (score_sum[row] + row_reach * float(reward))

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
        raise FileNotFoundError(f"No state_properties shards found for level {level}. Run build_terminal_shards.py first.")
    for mask in masks:
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            n_rows = len(upper)
        save_shard(level, mask, merge=True,
                   expected_score_after_check=np.zeros(n_rows, dtype=np.float64),
                   p_top_bonus_after=(upper >= UPPER_BONUS_THRESHOLD).astype(np.float64))


def load_backward_scalar_next_tables(level: int) -> dict[int, dict[str, np.ndarray]]:
    out = {}
    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)
            expected_after = shard[EXPECTED_SCORE_AFTER_CHECK].astype(np.float64)
            p_top_bonus = shard[P_TOP_BONUS_AFTER].astype(np.float64)
        out[mask] = {"row_for": make_row_lookup(upper, eligible),
                     EXPECTED_SCORE_AFTER_CHECK: expected_after,
                     P_TOP_BONUS_AFTER: p_top_bonus}
    return out


def compute_backward_scalar_level(level: int) -> None:
    next_tables = load_backward_scalar_next_tables(level + 1)
    for mask in tqdm(list_masks_for_level(level), desc=f"backward scalars L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
        expected_after = np.zeros(n_rows, dtype=np.float64)
        p_top_bonus = np.zeros(n_rows, dtype=np.float64)
        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, _, reward_all, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)
            for row in range(n_rows):
                s = row_slice(kernel, row)
                ev = 0.0
                p_bonus = 0.0
                for cat, reward, nu, ne, num in zip(category_all[s], reward_all[s], next_upper_all[s], next_eligible_all[s], numerator_all[s]):
                    p = float(num) / denom
                    next_mask = mask | (1 << int(cat))
                    tables = next_tables[next_mask]
                    next_row = int(tables["row_for"][int(nu), int(ne)])
                    ev += p * (float(reward) + float(tables[EXPECTED_SCORE_AFTER_CHECK][next_row]))
                    p_bonus += p * float(tables[P_TOP_BONUS_AFTER][next_row])
                expected_after[row] = ev
                p_top_bonus[row] = p_bonus
        save_shard(level, mask, merge=True,
                   expected_score_after_check=expected_after,
                   p_top_bonus_after=p_top_bonus)


def run_backward_scalars() -> None:
    seed_backward_scalars()
    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_backward_scalar_level(level)
    print("Done. Wrote expected_score_after_check, p_top_bonus_after.")


# ---------------------------------------------------------------------
# Forward/backward total score distributions
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
    save_shard(0, 0, merge=True, score_dist_before=dist)


def propagate_forward_score_dist_level(level: int) -> None:
    next_meta = load_level_metadata(level + 1)
    next_dist = {m: np.zeros((int(meta["n_rows"]), N_SCORE_BINS), dtype=np.float32) for m, meta in next_meta.items()}
    for mask in tqdm(list_masks_for_level(level), desc=f"score dist before L{level:02d}"):
        with load_shard(level, mask) as shard:
            current_dist = shard[SCORE_DIST_BEFORE].astype(np.float32)
            reach = shard[REACH_PROB].astype(np.float64)
        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, _, reward_all, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)
            for row in range(current_dist.shape[0]):
                if reach[row] == 0:
                    continue
                src = current_dist[row]
                if not np.any(src):
                    continue
                s = row_slice(kernel, row)
                for cat, reward, nu, ne, num in zip(category_all[s], reward_all[s], next_upper_all[s], next_eligible_all[s], numerator_all[s]):
                    r = int(reward)
                    p = float(num) / denom
                    next_mask = mask | (1 << int(cat))
                    next_row = int(next_meta[next_mask]["row_for"][int(nu), int(ne)])
                    if r == 0:
                        next_dist[next_mask][next_row] += p * src
                    else:
                        next_dist[next_mask][next_row, r:] += p * src[: N_SCORE_BINS - r]
    for mask in sorted(next_meta):
        save_shard(level + 1, mask, merge=True, score_dist_before=next_dist[mask])


def run_forward_score_dist() -> None:
    seed_forward_score_dist()
    for level in range(NUM_CATEGORIES):
        propagate_forward_score_dist_level(level)
    print("Done. Wrote score_dist_before.")


def seed_backward_score_dist() -> None:
    level = NUM_CATEGORIES
    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}. Run build_terminal_shards.py first.")
    for mask in masks:
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
        dist = np.zeros((n_rows, N_SCORE_BINS), dtype=np.float32)
        dist[:, 0] = 1.0
        save_shard(level, mask, merge=True, score_dist_after=dist)


def load_backward_score_next_tables(level: int) -> dict[int, dict[str, np.ndarray]]:
    out = {}
    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)
            dist = shard[SCORE_DIST_AFTER].astype(np.float32)
        out[mask] = {"row_for": make_row_lookup(upper, eligible), SCORE_DIST_AFTER: dist}
    return out


def compute_backward_score_dist_level(level: int) -> None:
    next_tables = load_backward_score_next_tables(level + 1)
    for mask in tqdm(list_masks_for_level(level), desc=f"score dist after L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
        out = np.zeros((n_rows, N_SCORE_BINS), dtype=np.float32)
        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, _, reward_all, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)
            for row in range(n_rows):
                row_out = out[row]
                s = row_slice(kernel, row)
                for cat, reward, nu, ne, num in zip(category_all[s], reward_all[s], next_upper_all[s], next_eligible_all[s], numerator_all[s]):
                    r = int(reward)
                    p = float(num) / denom
                    next_mask = mask | (1 << int(cat))
                    tables = next_tables[next_mask]
                    next_row = int(tables["row_for"][int(nu), int(ne)])
                    succ = tables[SCORE_DIST_AFTER][next_row]
                    if r == 0:
                        row_out += p * succ
                    else:
                        row_out[r:] += p * succ[: N_SCORE_BINS - r]
        save_shard(level, mask, merge=True, score_dist_after=out.astype(np.float32))


def run_backward_score_dist() -> None:
    seed_backward_score_dist()
    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_backward_score_dist_level(level)
    print("Done. Wrote score_dist_after.")


# ---------------------------------------------------------------------
# Per-box distributions
# ---------------------------------------------------------------------

def seed_backward_box_dist(category: int) -> None:
    level = NUM_CATEGORIES
    name = box_after_name(category)
    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}. Run build_terminal_shards.py first.")
    for mask in masks:
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
        save_shard(level, mask, merge=True, **{name: np.zeros((n_rows, N_BOX_BINS), dtype=np.float32)})


def load_backward_box_next_tables(level: int, category: int) -> dict[int, dict[str, np.ndarray]]:
    name = box_after_name(category)
    out = {}
    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)
            dist = shard[name].astype(np.float32)
        out[mask] = {"row_for": make_row_lookup(upper, eligible), name: dist}
    return out


def compute_backward_box_dist_level(level: int, category: int) -> None:
    name = box_after_name(category)
    next_tables = load_backward_box_next_tables(level + 1, category)
    for mask in tqdm(list_masks_for_level(level), desc=f"{name} L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
        out = np.zeros((n_rows, N_BOX_BINS), dtype=np.float32)
        if mask & (1 << category):
            save_shard(level, mask, merge=True, **{name: out})
            continue
        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, box_points_all, _, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)
            for row in range(n_rows):
                row_out = out[row]
                s = row_slice(kernel, row)
                for cat, pts, nu, ne, num in zip(category_all[s], box_points_all[s], next_upper_all[s], next_eligible_all[s], numerator_all[s]):
                    p = float(num) / denom
                    c = int(cat)
                    if c == category:
                        row_out[int(pts)] += p
                    else:
                        next_mask = mask | (1 << c)
                        tables = next_tables[next_mask]
                        next_row = int(tables["row_for"][int(nu), int(ne)])
                        row_out += p * tables[name][next_row]
        save_shard(level, mask, merge=True, **{name: out.astype(np.float32)})


def run_backward_box_dist(category: int) -> None:
    print(f"Computing after-distribution for {category}: {CATEGORY_NAMES[category]}")
    seed_backward_box_dist(category)
    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_backward_box_dist_level(level, category)
    print(f"Done. Wrote {box_after_name(category)}.")


def seed_forward_box_dist(category: int) -> None:
    name = box_before_name(category)
    with load_shard(0, 0) as shard:
        n_rows = int(shard["upper_total"].shape[0])
    save_shard(0, 0, merge=True, **{name: np.zeros((n_rows, N_BOX_BINS), dtype=np.float32)})


def propagate_forward_box_dist_level(level: int, category: int) -> None:
    name = box_before_name(category)
    next_meta = load_level_metadata(level + 1)
    next_dist = {m: np.zeros((int(meta["n_rows"]), N_BOX_BINS), dtype=np.float32) for m, meta in next_meta.items()}
    for mask in tqdm(list_masks_for_level(level), desc=f"{name} L{level:02d}"):
        with load_shard(level, mask) as shard:
            current_dist = shard[name].astype(np.float32)
            reach = shard[REACH_PROB].astype(np.float64)
        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, box_points_all, _, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)
            for row in range(current_dist.shape[0]):
                row_reach = float(reach[row])
                if row_reach == 0:
                    continue
                src = current_dist[row]
                s = row_slice(kernel, row)
                for cat, pts, nu, ne, num in zip(category_all[s], box_points_all[s], next_upper_all[s], next_eligible_all[s], numerator_all[s]):
                    p = float(num) / denom
                    c = int(cat)
                    next_mask = mask | (1 << c)
                    next_row = int(next_meta[next_mask]["row_for"][int(nu), int(ne)])
                    if c == category:
                        next_dist[next_mask][next_row, int(pts)] += row_reach * p
                    else:
                        next_dist[next_mask][next_row] += p * src
    for mask in sorted(next_meta):
        save_shard(level + 1, mask, merge=True, **{name: next_dist[mask].astype(np.float32)})


def run_forward_box_dist(category: int) -> None:
    print(f"Computing before-distribution for {category}: {CATEGORY_NAMES[category]}")
    seed_forward_box_dist(category)
    for level in range(NUM_CATEGORIES):
        propagate_forward_box_dist_level(level, category)
    print(f"Done. Wrote {box_before_name(category)}.")


# ---------------------------------------------------------------------
# Extra Yahtzee bonus distributions
# ---------------------------------------------------------------------

def seed_forward_yahtzee_bonus_dist() -> None:
    with load_shard(0, 0) as shard:
        n_rows = int(shard["upper_total"].shape[0])
        upper = shard["upper_total"]
        eligible = shard["yahtzee_eligible"]
    dist = np.zeros((n_rows, N_YAHTZEE_BONUS_BINS), dtype=np.float32)
    rows = np.where((upper == 0) & (~eligible))[0]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one initial row; found {len(rows)}")
    dist[int(rows[0]), 0] = 1.0
    save_shard(0, 0, merge=True, yahtzee_bonus_dist_before=dist)


def propagate_forward_yahtzee_bonus_dist_level(level: int) -> None:
    next_meta = load_level_metadata(level + 1)
    next_dist = {m: np.zeros((int(meta["n_rows"]), N_YAHTZEE_BONUS_BINS), dtype=np.float32) for m, meta in next_meta.items()}
    for mask in tqdm(list_masks_for_level(level), desc=f"yahtzee bonus before L{level:02d}"):
        with load_shard(level, mask) as shard:
            current_dist = shard[YAHTZEE_BONUS_DIST_BEFORE].astype(np.float32)
            reach = shard[REACH_PROB].astype(np.float64)
            upper_arr = shard["upper_total"].astype(np.int64)
        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, box_points_all, reward_all, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)
            for row in range(current_dist.shape[0]):
                if reach[row] == 0:
                    continue
                src = current_dist[row]
                if not np.any(src):
                    continue
                upper = int(upper_arr[row])
                s = row_slice(kernel, row)
                for cat, pts, reward, nu, ne, num in zip(category_all[s], box_points_all[s], reward_all[s], next_upper_all[s], next_eligible_all[s], numerator_all[s]):
                    p = float(num) / denom
                    c = int(cat)
                    bonus = extra_yahtzee_bonus_count_from_outcome(upper=upper, category=c, box_points=int(pts), reward=int(reward))
                    next_mask = mask | (1 << c)
                    next_row = int(next_meta[next_mask]["row_for"][int(nu), int(ne)])
                    if bonus == 0:
                        next_dist[next_mask][next_row] += p * src
                    else:
                        next_dist[next_mask][next_row, bonus:] += p * src[: N_YAHTZEE_BONUS_BINS - bonus]
    for mask in sorted(next_meta):
        save_shard(level + 1, mask, merge=True, yahtzee_bonus_dist_before=next_dist[mask])


def run_forward_yahtzee_bonus_dist() -> None:
    seed_forward_yahtzee_bonus_dist()
    for level in range(NUM_CATEGORIES):
        propagate_forward_yahtzee_bonus_dist_level(level)
    print("Done. Wrote yahtzee_bonus_dist_before.")


def seed_backward_yahtzee_bonus_dist() -> None:
    level = NUM_CATEGORIES
    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}. Run build_terminal_shards.py first.")
    for mask in masks:
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
        dist = np.zeros((n_rows, N_YAHTZEE_BONUS_BINS), dtype=np.float32)
        dist[:, 0] = 1.0
        save_shard(level, mask, merge=True, yahtzee_bonus_dist_after=dist)


def load_backward_yahtzee_bonus_next_tables(level: int) -> dict[int, dict[str, np.ndarray]]:
    out = {}
    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)
            dist = shard[YAHTZEE_BONUS_DIST_AFTER].astype(np.float32)
        out[mask] = {"row_for": make_row_lookup(upper, eligible), YAHTZEE_BONUS_DIST_AFTER: dist}
    return out


def compute_backward_yahtzee_bonus_dist_level(level: int) -> None:
    next_tables = load_backward_yahtzee_bonus_next_tables(level + 1)
    for mask in tqdm(list_masks_for_level(level), desc=f"yahtzee bonus after L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
            upper_arr = shard["upper_total"].astype(np.int64)
        out = np.zeros((n_rows, N_YAHTZEE_BONUS_BINS), dtype=np.float32)
        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, box_points_all, reward_all, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)
            for row in range(n_rows):
                upper = int(upper_arr[row])
                row_out = out[row]
                s = row_slice(kernel, row)
                for cat, pts, reward, nu, ne, num in zip(category_all[s], box_points_all[s], reward_all[s], next_upper_all[s], next_eligible_all[s], numerator_all[s]):
                    p = float(num) / denom
                    c = int(cat)
                    bonus = extra_yahtzee_bonus_count_from_outcome(upper=upper, category=c, box_points=int(pts), reward=int(reward))
                    next_mask = mask | (1 << c)
                    tables = next_tables[next_mask]
                    next_row = int(tables["row_for"][int(nu), int(ne)])
                    succ = tables[YAHTZEE_BONUS_DIST_AFTER][next_row]
                    if bonus == 0:
                        row_out += p * succ
                    else:
                        row_out[bonus:] += p * succ[: N_YAHTZEE_BONUS_BINS - bonus]
        save_shard(level, mask, merge=True, yahtzee_bonus_dist_after=out.astype(np.float32))


def run_backward_yahtzee_bonus_dist() -> None:
    seed_backward_yahtzee_bonus_dist()
    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_backward_yahtzee_bonus_dist_level(level)
    print("Done. Wrote yahtzee_bonus_dist_after.")



# ---------------------------------------------------------------------
# Sparse final-outcome distributions
# ---------------------------------------------------------------------

def final_outcome_dist_path(level: int, mask: int) -> str:
    return os.path.join(FINAL_OUTCOME_DIST_DIR, f"level_{level:02d}", f"{mask:013b}.npz")


def pack_final_outcome_key(score, yahtzee_units, flags):
    return (
        np.asarray(score, dtype=np.uint32)
        | (np.asarray(yahtzee_units, dtype=np.uint32) << YAHTZEE_UNIT_SHIFT)
        | (np.asarray(flags, dtype=np.uint32) << FLAGS_SHIFT)
    )


def unpack_final_outcome_keys(keys: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    keys = np.asarray(keys, dtype=np.uint32)
    score = (keys & SCORE_MASK).astype(np.int64)
    yahtzee_units = ((keys >> YAHTZEE_UNIT_SHIFT) & YAHTZEE_UNIT_MASK).astype(np.int64)
    flags = (keys >> FLAGS_SHIFT).astype(np.int64)
    return score, yahtzee_units, flags


def outcome_flags_from_transition(*, upper: int, category: int, box_points: int) -> int:
    flags = 0

    # Treat joker fills exactly like normal fills: if the box gets positive
    # points, set the corresponding "made this box" flag.
    if category == LARGE_STRAIGHT and box_points > 0:
        flags |= FLAG_LARGE_STRAIGHT
    elif category == SMALL_STRAIGHT and box_points > 0:
        flags |= FLAG_SMALL_STRAIGHT
    elif category == FULL_HOUSE and box_points > 0:
        flags |= FLAG_FULL_HOUSE
    elif category == FOUR_KIND and box_points > 0:
        flags |= FLAG_FOUR_KIND
    elif category == THREE_KIND and box_points > 0:
        flags |= FLAG_THREE_KIND

    if category <= SIXES and upper < UPPER_BONUS_THRESHOLD and upper + box_points >= UPPER_BONUS_THRESHOLD:
        flags |= FLAG_TOP_BONUS

    return flags


def yahtzee_units_from_transition(*, upper: int, category: int, box_points: int, reward: int) -> int:
    units = 0
    if category == YAHTZEE and box_points == YAHTZEE_POINTS:
        units += 1
    units += extra_yahtzee_bonus_count_from_outcome(
        upper=upper,
        category=category,
        box_points=box_points,
        reward=reward,
    )
    return units


def transform_final_outcome_keys(
    keys: np.ndarray,
    *,
    reward: int,
    yahtzee_units_add: int,
    flags_add: int,
) -> np.ndarray:
    score, yahtzee_units, flags = unpack_final_outcome_keys(keys)
    return pack_final_outcome_key(
        score + int(reward),
        yahtzee_units + int(yahtzee_units_add),
        flags | int(flags_add),
    )


def combine_sparse_entries(keys_parts: list[np.ndarray], probs_parts: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    if not keys_parts:
        return np.empty(0, dtype=np.uint32), np.empty(0, dtype=np.float32)

    keys = np.concatenate(keys_parts).astype(np.uint32, copy=False)
    probs = np.concatenate(probs_parts).astype(np.float64, copy=False)

    if len(keys) == 0:
        return keys.astype(np.uint32), probs.astype(np.float32)

    order = np.argsort(keys, kind="stable")
    keys = keys[order]
    probs = probs[order]

    starts = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1]) + 1]
    out_keys = keys[starts]
    out_probs = np.add.reduceat(probs, starts).astype(np.float32)

    # Drop tiny numerical noise, but keep the usual float32-level mass.
    keep = out_probs > 0.0
    return out_keys[keep].astype(np.uint32), out_probs[keep].astype(np.float32)


def save_final_outcome_sparse_shard(
    level: int,
    mask: int,
    row_keys: list[np.ndarray],
    row_probs: list[np.ndarray],
) -> None:
    if len(row_keys) != len(row_probs):
        raise ValueError("row_keys and row_probs must have the same length")

    n_rows = len(row_keys)
    lengths = np.array([len(k) for k in row_keys], dtype=np.int64)
    offsets = np.empty(n_rows + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(lengths, out=offsets[1:])

    if int(offsets[-1]) == 0:
        keys = np.empty(0, dtype=np.uint32)
        probs = np.empty(0, dtype=np.float32)
    else:
        keys = np.concatenate(row_keys).astype(np.uint32, copy=False)
        probs = np.concatenate(row_probs).astype(np.float32, copy=False)

    path = final_outcome_dist_path(level, mask)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.npz"
    np.savez_compressed(
        tmp,
        **{
            FINAL_OUTCOME_OFFSETS: offsets,
            FINAL_OUTCOME_KEYS: keys,
            FINAL_OUTCOME_PROBS: probs,
        },
    )
    os.replace(tmp, path)


def load_final_outcome_sparse_shard(level: int, mask: int) -> dict[str, np.ndarray]:
    path = final_outcome_dist_path(level, mask)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing final-outcome distribution shard: {path}")
    with np.load(path) as shard:
        return {
            FINAL_OUTCOME_OFFSETS: shard[FINAL_OUTCOME_OFFSETS].astype(np.int64),
            FINAL_OUTCOME_KEYS: shard[FINAL_OUTCOME_KEYS].astype(np.uint32),
            FINAL_OUTCOME_PROBS: shard[FINAL_OUTCOME_PROBS].astype(np.float32),
        }


def final_outcome_row_slice(table: dict[str, np.ndarray], row: int) -> slice:
    offsets = table[FINAL_OUTCOME_OFFSETS]
    return slice(int(offsets[row]), int(offsets[row + 1]))


def seed_backward_final_outcome_dist() -> None:
    level = NUM_CATEGORIES
    masks = list_masks_for_level(level)
    if not masks:
        raise FileNotFoundError(f"No state_properties shards found for level {level}. Run build_terminal_shards.py first.")

    zero_key = np.array([pack_final_outcome_key(0, 0, 0)], dtype=np.uint32)
    one_prob = np.array([1.0], dtype=np.float32)

    for mask in masks:
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
        row_keys = [zero_key.copy() for _ in range(n_rows)]
        row_probs = [one_prob.copy() for _ in range(n_rows)]
        save_final_outcome_sparse_shard(level, mask, row_keys, row_probs)


def load_backward_final_outcome_next_tables(level: int) -> dict[int, dict[str, np.ndarray]]:
    out = {}
    for mask in list_masks_for_level(level):
        with load_shard(level, mask) as shard:
            upper = shard["upper_total"].astype(np.int64)
            eligible = shard["yahtzee_eligible"].astype(bool)
        sparse = load_final_outcome_sparse_shard(level, mask)
        sparse["row_for"] = make_row_lookup(upper, eligible)
        out[mask] = sparse
    return out


def compute_backward_final_outcome_dist_level(level: int) -> None:
    next_tables = load_backward_final_outcome_next_tables(level + 1)

    for mask in tqdm(list_masks_for_level(level), desc=f"final outcome after L{level:02d}"):
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
            upper_arr = shard["upper_total"].astype(np.int64)

        row_keys_out: list[np.ndarray] = []
        row_probs_out: list[np.ndarray] = []

        with load_turn_kernel(level, mask) as kernel:
            denom, category_all, box_points_all, reward_all, next_upper_all, next_eligible_all, numerator_all = kernel_prob(kernel)

            for row in range(n_rows):
                upper = int(upper_arr[row])
                keys_parts: list[np.ndarray] = []
                probs_parts: list[np.ndarray] = []

                s = row_slice(kernel, row)
                for cat, pts, reward, nu, ne, num in zip(
                    category_all[s],
                    box_points_all[s],
                    reward_all[s],
                    next_upper_all[s],
                    next_eligible_all[s],
                    numerator_all[s],
                ):
                    c = int(cat)
                    pts_i = int(pts)
                    reward_i = int(reward)
                    p = float(num) / denom

                    next_mask = mask | (1 << c)
                    tables = next_tables[next_mask]
                    next_row = int(tables["row_for"][int(nu), int(ne)])
                    rs = final_outcome_row_slice(tables, next_row)
                    succ_keys = tables[FINAL_OUTCOME_KEYS][rs]
                    succ_probs = tables[FINAL_OUTCOME_PROBS][rs]

                    flags_add = outcome_flags_from_transition(
                        upper=upper,
                        category=c,
                        box_points=pts_i,
                    )
                    y_add = yahtzee_units_from_transition(
                        upper=upper,
                        category=c,
                        box_points=pts_i,
                        reward=reward_i,
                    )

                    keys_parts.append(
                        transform_final_outcome_keys(
                            succ_keys,
                            reward=reward_i,
                            yahtzee_units_add=y_add,
                            flags_add=flags_add,
                        )
                    )
                    probs_parts.append((p * succ_probs).astype(np.float32))

                keys, probs = combine_sparse_entries(keys_parts, probs_parts)
                row_keys_out.append(keys)
                row_probs_out.append(probs)

        save_final_outcome_sparse_shard(level, mask, row_keys_out, row_probs_out)


def print_initial_final_outcome_summary(max_rows: int = 20) -> None:
    with load_shard(0, 0) as state_shard:
        upper = state_shard["upper_total"]
        eligible = state_shard["yahtzee_eligible"]
    rows = np.where((upper == 0) & (~eligible))[0]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one initial row; found {len(rows)}")
    row = int(rows[0])

    table = load_final_outcome_sparse_shard(0, 0)
    s = final_outcome_row_slice(table, row)
    keys = table[FINAL_OUTCOME_KEYS][s]
    probs = table[FINAL_OUTCOME_PROBS][s].astype(np.float64)
    score, yahtzee_units, flags = unpack_final_outcome_keys(keys)

    print()
    print("initial final-outcome distribution")
    print(f"  nonzero outcomes: {len(keys):,}")
    print(f"  total mass:       {float(probs.sum()):.12f}")
    print(f"  mean score:       {float(probs @ score):.12f}")
    print(f"  p top bonus:      {float(probs[(flags & FLAG_TOP_BONUS) != 0].sum()):.12f}")
    print(f"  p yahtzee 50+:    {float(probs[yahtzee_units >= 1].sum()):.12f}")
    print(f"  p extra yahtzee:  {float(probs[yahtzee_units >= 2].sum()):.12f}")

    if max_rows > 0:
        order = np.argsort(probs)[::-1][:max_rows]
        print()
        print(f"top {len(order)} outcomes by probability:")
        for i in order:
            print(
                f"  p={probs[i]:.8f}  "
                f"score={int(score[i]):4d}  "
                f"yahtzee_units={int(yahtzee_units[i]):2d}  "
                f"flags={int(flags[i]):02x}"
            )


def run_backward_final_outcome_dist() -> None:
    seed_backward_final_outcome_dist()
    for level in range(NUM_CATEGORIES - 1, -1, -1):
        compute_backward_final_outcome_dist_level(level)
    print("Done. Wrote sparse final-outcome distributions.")
    print_initial_final_outcome_summary()



# ---------------------------------------------------------------------
# Reduced point / actual score joint distributions
# ---------------------------------------------------------------------

def reduced_point_dist_path(level: int, mask: int) -> str:
    return os.path.join(REDUCED_POINT_DIST_DIR, f"level_{level:02d}", f"{mask:013b}.npz")


def pack_reduced_point_key(score, reduced_points):
    score = np.asarray(score, dtype=np.uint32)
    reduced_points = np.asarray(reduced_points, dtype=np.uint32)
    if np.any(score > SCORE_MASK):
        raise ValueError("score does not fit in SCORE_BITS")
    if np.any(reduced_points > REDUCED_POINT_MASK):
        raise ValueError("reduced_points does not fit in packed key")
    return score | (reduced_points << REDUCED_POINT_SHIFT)


def unpack_reduced_point_keys(keys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    keys = np.asarray(keys, dtype=np.uint32)
    score = (keys & SCORE_MASK).astype(np.int64)
    reduced_points = ((keys >> REDUCED_POINT_SHIFT) & REDUCED_POINT_MASK).astype(np.int64)
    return score, reduced_points


def reduced_points_from_components(yahtzee_units: np.ndarray, flags: np.ndarray) -> np.ndarray:
    """Compute the simple reduced point system from final-outcome components.

    yahtzee_units convention:
        0 = Yahtzee box scored 0
        1 = Yahtzee box scored 50, with no extra +100 bonuses
        k = Yahtzee box scored 50, with k - 1 extra +100 bonuses
    """
    yahtzee_units = np.asarray(yahtzee_units, dtype=np.int64)
    flags = np.asarray(flags, dtype=np.int64)

    reduced_points = np.zeros_like(yahtzee_units, dtype=np.int64)

    reduced_points += REDUCED_POINTS_EXTRA_YAHTZEE_BONUS * np.maximum(yahtzee_units - 1, 0)
    reduced_points += REDUCED_POINTS_YAHTZEE * (yahtzee_units >= 1)
    reduced_points += REDUCED_POINTS_LARGE_STRAIGHT * ((flags & FLAG_LARGE_STRAIGHT) != 0)
    reduced_points += REDUCED_POINTS_TOP_BONUS * ((flags & FLAG_TOP_BONUS) != 0)
    reduced_points += REDUCED_POINTS_SMALL_STRAIGHT * ((flags & FLAG_SMALL_STRAIGHT) != 0)
    reduced_points += REDUCED_POINTS_FULL_HOUSE * ((flags & FLAG_FULL_HOUSE) != 0)
    reduced_points += REDUCED_POINTS_THREE_KIND * ((flags & FLAG_THREE_KIND) != 0)
    reduced_points += REDUCED_POINTS_FOUR_KIND * ((flags & FLAG_FOUR_KIND) != 0)

    return reduced_points.astype(np.int64)


def reduced_point_keys_from_final_outcome_keys(final_keys: np.ndarray) -> np.ndarray:
    score, yahtzee_units, flags = unpack_final_outcome_keys(final_keys)
    reduced_points = reduced_points_from_components(yahtzee_units, flags)
    return pack_reduced_point_key(score, reduced_points)


def collapse_final_outcome_row_to_reduced_points(
    final_keys: np.ndarray,
    final_probs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    keys = reduced_point_keys_from_final_outcome_keys(final_keys)
    return combine_sparse_entries([keys], [final_probs])


def save_reduced_point_sparse_shard(
    level: int,
    mask: int,
    row_keys: list[np.ndarray],
    row_probs: list[np.ndarray],
) -> None:
    if len(row_keys) != len(row_probs):
        raise ValueError("row_keys and row_probs must have the same length")

    n_rows = len(row_keys)
    lengths = np.array([len(k) for k in row_keys], dtype=np.int64)
    offsets = np.empty(n_rows + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(lengths, out=offsets[1:])

    if int(offsets[-1]) == 0:
        keys = np.empty(0, dtype=np.uint32)
        probs = np.empty(0, dtype=np.float32)
    else:
        keys = np.concatenate(row_keys).astype(np.uint32, copy=False)
        probs = np.concatenate(row_probs).astype(np.float32, copy=False)

    path = reduced_point_dist_path(level, mask)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.npz"
    np.savez_compressed(
        tmp,
        **{
            REDUCED_POINT_OFFSETS: offsets,
            REDUCED_POINT_KEYS: keys,
            REDUCED_POINT_PROBS: probs,
        },
    )
    os.replace(tmp, path)


def load_reduced_point_sparse_shard(level: int, mask: int) -> dict[str, np.ndarray]:
    path = reduced_point_dist_path(level, mask)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing reduced-point distribution shard: {path}")
    with np.load(path) as shard:
        return {
            REDUCED_POINT_OFFSETS: shard[REDUCED_POINT_OFFSETS].astype(np.int64),
            REDUCED_POINT_KEYS: shard[REDUCED_POINT_KEYS].astype(np.uint32),
            REDUCED_POINT_PROBS: shard[REDUCED_POINT_PROBS].astype(np.float32),
        }


def reduced_point_row_slice(table: dict[str, np.ndarray], row: int) -> slice:
    offsets = table[REDUCED_POINT_OFFSETS]
    return slice(int(offsets[row]), int(offsets[row + 1]))


def compute_reduced_point_dist_shard(level: int, mask: int) -> tuple[int, int]:
    final_table = load_final_outcome_sparse_shard(level, mask)
    offsets = final_table[FINAL_OUTCOME_OFFSETS]
    n_rows = len(offsets) - 1

    row_keys_out: list[np.ndarray] = []
    row_probs_out: list[np.ndarray] = []

    for row in range(n_rows):
        s = final_outcome_row_slice(final_table, row)
        keys, probs = collapse_final_outcome_row_to_reduced_points(
            final_table[FINAL_OUTCOME_KEYS][s],
            final_table[FINAL_OUTCOME_PROBS][s],
        )
        row_keys_out.append(keys)
        row_probs_out.append(probs)

    save_reduced_point_sparse_shard(level, mask, row_keys_out, row_probs_out)
    return n_rows, int(sum(len(keys) for keys in row_keys_out))


def initial_row() -> int:
    with load_shard(0, 0) as shard:
        upper = shard["upper_total"]
        eligible = shard["yahtzee_eligible"]
    rows = np.where((upper == 0) & (~eligible))[0]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one initial row; found {len(rows)}")
    return int(rows[0])


def run_reduced_point_dist(*, start_only: bool = False) -> None:
    if start_only:
        n_rows, n_entries = compute_reduced_point_dist_shard(0, 0)
        print(
            "Done. Wrote start-state reduced-point/score distribution to "
            f"{reduced_point_dist_path(0, 0)}. rows={n_rows:,}, entries={n_entries:,}"
        )
        print_initial_reduced_point_summary()
        return

    total_rows = 0
    total_entries = 0

    for level in range(NUM_CATEGORIES + 1):
        for mask in tqdm(list_masks_for_level(level), desc=f"reduced point dist L{level:02d}"):
            n_rows, n_entries = compute_reduced_point_dist_shard(level, mask)
            total_rows += n_rows
            total_entries += n_entries

    print(
        "Done. Wrote sparse reduced-point/score distributions to "
        f"{REDUCED_POINT_DIST_DIR}. rows={total_rows:,}, entries={total_entries:,}"
    )
    print_initial_reduced_point_summary()


def initial_reduced_point_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    table = load_reduced_point_sparse_shard(0, 0)
    s = reduced_point_row_slice(table, initial_row())
    keys = table[REDUCED_POINT_KEYS][s]
    probs = table[REDUCED_POINT_PROBS][s].astype(np.float64)
    score, reduced_points = unpack_reduced_point_keys(keys)
    order = np.lexsort((score, reduced_points))
    return reduced_points[order], score[order], probs[order]


def print_initial_reduced_point_summary(max_rows: int = 20) -> None:
    reduced_points, score, probs = initial_reduced_point_arrays()

    print()
    print("initial reduced-point/score distribution")
    print(f"  nonzero outcomes:     {len(probs):,}")
    print(f"  total mass:           {float(probs.sum()):.12f}")
    print(f"  mean score:           {float(probs @ score):.12f}")
    print(f"  mean reduced points:  {float(probs @ reduced_points):.12f}")

    marginal = np.bincount(reduced_points.astype(np.int64), weights=probs)
    print()
    print("reduced-point marginal:")
    for points, prob in enumerate(marginal):
        if prob > 0:
            print(f"  {points:2d}: {prob:.12f}")

    if max_rows > 0:
        order = np.argsort(probs)[::-1][:max_rows]
        print()
        print(f"top {len(order)} joint outcomes by probability:")
        for i in order:
            print(
                f"  p={probs[i]:.8f}  "
                f"reduced_points={int(reduced_points[i]):2d}  "
                f"score={int(score[i]):4d}"
            )

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def run_categories(args, fn) -> None:
    if args.all:
        categories = range(NUM_CATEGORIES)
    elif args.category is not None:
        categories = [category_from_arg(args.category)]
    else:
        raise SystemExit("Pass --category <0..12/name> or --all.")
    for category in categories:
        fn(category)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("forward-scalars")
    sub.add_parser("backward-scalars")
    sub.add_parser("forward-score-dist")
    sub.add_parser("backward-score-dist")
    sub.add_parser("forward-yahtzee-bonus-dist")
    sub.add_parser("backward-yahtzee-bonus-dist")
    sub.add_parser("backward-final-outcome-dist")

    p_reduced = sub.add_parser("reduced-point-dist")
    p_reduced.add_argument("--start-only", action="store_true")

    p_reduced_summary = sub.add_parser("reduced-point-summary")
    p_reduced_summary.add_argument("--max-rows", type=int, default=20)

    p_box_after = sub.add_parser("backward-box-dist")
    p_box_after.add_argument("--category", type=str, default=None)
    p_box_after.add_argument("--all", action="store_true")

    p_box_before = sub.add_parser("forward-box-dist")
    p_box_before.add_argument("--category", type=str, default=None)
    p_box_before.add_argument("--all", action="store_true")

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
        run_categories(args, run_backward_box_dist)
    elif args.command == "forward-box-dist":
        run_categories(args, run_forward_box_dist)
    elif args.command == "forward-yahtzee-bonus-dist":
        run_forward_yahtzee_bonus_dist()
    elif args.command == "backward-yahtzee-bonus-dist":
        run_backward_yahtzee_bonus_dist()
    elif args.command == "backward-final-outcome-dist":
        run_backward_final_outcome_dist()
    elif args.command == "reduced-point-dist":
        run_reduced_point_dist(start_only=args.start_only)
    elif args.command == "reduced-point-summary":
        print_initial_reduced_point_summary(max_rows=args.max_rows)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
