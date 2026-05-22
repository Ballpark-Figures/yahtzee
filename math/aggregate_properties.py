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
"""

from __future__ import annotations

import argparse
import os

import numpy as np
from tqdm import tqdm

from constants import (
    NUM_CATEGORIES,
    CATEGORY_NAMES,
    SIXES,
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
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
