"""Yahtzee state-explorer helpers (shared source of truth).

Extracted verbatim from ``math/notebooks/state_explorer.ipynb`` so both the
notebook and other tooling (e.g. the animation cache generator in
``animations/assets/dp_data.py``) call the SAME query helpers over the solved
game rather than reinventing the math.

Contract (same as the notebook's Cell 1): the CALLER must ensure the current
working directory is the ``math/`` project dir and that ``math/`` is on
``sys.path`` BEFORE importing this module, because the solver data paths are
relative to ``math/`` and ``precomputed`` loads pickles from ``data/`` at import
time. This module is otherwise side-effect free (no chdir).
"""

from pathlib import Path
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from constants import *
from precomputed import (
    ALL_DICE_STATES, ALL_DICE_FREQS, ALL_KEEPS, KEEP_IDX, KEEPS_FOR_DICE,
    REROLL_OUTCOMES, DICE_IDX,
    dice_values_to_idx, dice_idx_to_values, dice_idx_to_vec, dice_vec_to_idx,
    SCORE_ROWS, JOKER_SCORE_ROWS, IS_YAHTZEE_T, YAHTZEE_FACE_T,
)
from reduced_game_state import ReducedGameState
from state_properties import STATE_PROPERTIES_DIR, shard_path, load_shard, row_index
from value_iteration import load_V_next, REROLL_MATRIX, REROLL_OFFSETS, REROLL_PAIR_KEEPS


# ## Basic display helpers

def cat_name(c):
    return CATEGORY_NAMES[int(c)]

def mask_from_categories(categories):
    '''
    categories can be ints or names from CATEGORY_NAMES.
    Example:
        mask_from_categories(["Ones", "Twos", YAHTZEE])
    '''
    mask = 0
    for c in categories:
        if isinstance(c, str):
            c = CATEGORY_NAMES.index(c)
        mask |= 1 << int(c)
    return mask

def categories_from_mask(mask):
    return [CATEGORY_NAMES[c] for c in range(NUM_CATEGORIES) if mask & (1 << c)]

def keep_to_values(keep_idx):
    keep = ALL_KEEPS[int(keep_idx)]
    return tuple(face for face, count in enumerate(keep, start=1) for _ in range(int(count)))

def vec_to_values(vec):
    return tuple(face for face, count in enumerate(vec, start=1) for _ in range(int(count)))

def roll_label(dice_idx):
    return dice_idx_to_values(int(dice_idx))

def state_level(state):
    return int(state.filled_mask).bit_count()

def describe_state(state):
    return {
        "filled_mask": f"{state.filled_mask:013b}",
        "level": state_level(state),
        "filled": categories_from_mask(state.filled_mask),
        "upper_total": state.upper_total,
        "yahtzee_eligible": bool(state.yahtzee_eligible),
    }


# ## Load the value-iteration payload for one state

def load_payload_for_state(state):
    level = state_level(state)
    path = Path(shard_path(level, state.filled_mask))
    if not path.exists():
        raise FileNotFoundError(
            f"Could not find {path}. Run value_iteration for level {level}, "
            "or check that this notebook is running from the project root."
        )
    return np.load(path)

def row_index_for_state(payload, state):
    try:
        return row_index(payload, int(state.upper_total), bool(state.yahtzee_eligible))
    except KeyError as e:
        sample = list(zip(payload["upper_total"][:10].tolist(),
                          payload["yahtzee_eligible"][:10].tolist()))
        raise KeyError(f"{e}. Available rows include: {sample} ...") from None

def get_state_row(state):
    payload = load_payload_for_state(state)
    row = row_index_for_state(payload, state)
    return payload, row

def state_value(state):
    payload, row = get_state_row(state)
    return float(payload["V"][row])


# ## Aggregate property helpers

def _resolve_category(category):
    if isinstance(category, str):
        if category in {"UpperBonus", "TopBonus", "Upper Bonus", "Top Bonus"}:
            return "UpperBonus"
        if category in {"YahtzeeBonus", "ExtraYahtzeeBonus", "Extra Yahtzee Bonus", "100PointYahtzeeBonus"}:
            return "YahtzeeBonus"
        return CATEGORY_NAMES.index(category)
    return int(category)

def box_before_name(category):
    c = _resolve_category(category)
    if isinstance(c, str):
        raise ValueError(f"{category!r} is a pseudo-category, not a real box array.")
    return f"box_score_dist_before_{c:02d}"

def box_after_name(category):
    c = _resolve_category(category)
    if isinstance(c, str):
        raise ValueError(f"{category!r} is a pseudo-category, not a real box array.")
    return f"box_score_dist_after_{c:02d}"

def available_arrays(state):
    payload, row = get_state_row(state)
    return list(payload.files)

def has_array(state, name):
    payload, row = get_state_row(state)
    return name in payload.files

def get_state_array_value(state, name):
    payload, row = get_state_row(state)
    if name not in payload.files:
        raise KeyError(f"{name!r} is not in this shard. Available arrays: {payload.files}")
    return payload[name][row]

def _normalize_distribution(dist, mass=None):
    dist = np.asarray(dist, dtype=np.float64)
    if mass is None:
        mass = float(dist.sum())
    if mass <= 0:
        return dist.copy(), float(mass)
    return dist / mass, float(mass)

def distribution_stats(dist, *, mass=None, normalize=True, values=None):
    """
    Return basic stats for a discrete distribution.

    If values is None, values are interpreted as 0, 1, ..., len(dist)-1.
    If normalize=True, stats are computed after normalizing by mass.
    The returned 'mass' is the original row mass.
    """
    dist = np.asarray(dist, dtype=np.float64)
    raw_mass = float(dist.sum()) if mass is None else float(mass)

    if normalize:
        probs, raw_mass = _normalize_distribution(dist, raw_mass)
    else:
        probs = dist

    if values is None:
        xs = np.arange(len(probs), dtype=np.float64)
    else:
        xs = np.asarray(values, dtype=np.float64)

    if probs.sum() <= 0:
        return {
            "mass": raw_mass,
            "mean": np.nan,
            "sd": np.nan,
            "q05": np.nan,
            "q25": np.nan,
            "median": np.nan,
            "q75": np.nan,
            "q95": np.nan,
            "min_nonzero": np.nan,
            "max_nonzero": np.nan,
            "n_nonzero": 0,
            "p_positive": 0.0,
        }

    prob_mass = float(probs.sum())
    mean = float(xs @ probs / prob_mass)
    var = float(((xs - mean) ** 2) @ probs / prob_mass)

    order = np.argsort(xs)
    xs_sorted = xs[order]
    probs_sorted = probs[order]
    cdf = np.cumsum(probs_sorted) / prob_mass

    def q(p):
        return float(xs_sorted[np.searchsorted(cdf, p, side="left")])

    nz = np.flatnonzero(probs > 0)
    return {
        "mass": raw_mass,
        "mean": mean,
        "sd": float(np.sqrt(max(var, 0.0))),
        "q05": q(0.05),
        "q25": q(0.25),
        "median": q(0.50),
        "q75": q(0.75),
        "q95": q(0.95),
        "min_nonzero": float(xs[nz[0]]) if len(nz) else np.nan,
        "max_nonzero": float(xs[nz[-1]]) if len(nz) else np.nan,
        "n_nonzero": int(len(nz)),
        "p_positive": float(probs[xs > 0].sum()) if len(xs) else 0.0,
    }

def distribution_table(dist, *, mass=None, normalize=True, min_prob=1e-8, values=None, value_name="score"):
    dist = np.asarray(dist, dtype=np.float64)
    if normalize:
        probs, raw_mass = _normalize_distribution(dist, mass)
    else:
        probs = dist
        raw_mass = float(dist.sum()) if mass is None else float(mass)

    if values is None:
        values = np.arange(len(probs), dtype=np.float64)
    else:
        values = np.asarray(values)

    rows = [
        {value_name: int(v) if float(v).is_integer() else float(v), "prob": float(p)}
        for v, p in zip(values, probs)
        if p >= min_prob
    ]
    df = pd.DataFrame(rows)
    if len(df):
        df["cdf"] = df["prob"].cumsum()
    return df

def score_distribution(state, when="after", *, conditional=True):
    """
    Return total score distribution for a state.

    when="before":
        Uses score_dist_before. This is stored unnormalized; if conditional=True,
        divide by reach_prob.

    when="after":
        Uses score_dist_after. This is already conditional on starting at state.
    """
    when = when.lower()
    payload, row = get_state_row(state)

    if when in {"before", "past", "pre"}:
        name = "score_dist_before"
        if name not in payload.files:
            raise KeyError(f"Missing {name}. Run aggregate_properties.py forward-score-dist.")
        dist = payload[name][row].astype(np.float64)
        mass = float(payload["reach_prob"][row]) if "reach_prob" in payload.files else float(dist.sum())
        if conditional:
            return _normalize_distribution(dist, mass)[0]
        return dist

    if when in {"after", "future", "post"}:
        name = "score_dist_after"
        if name not in payload.files:
            raise KeyError(f"Missing {name}. Run aggregate_properties.py backward-score-dist.")
        return payload[name][row].astype(np.float64)

    raise ValueError("when must be 'before' or 'after'")

def score_distribution_stats(state, when="after", *, conditional=True):
    dist = score_distribution(state, when=when, conditional=conditional)
    return distribution_stats(dist)

def score_distribution_table(state, when="after", *, conditional=True, min_prob=1e-8):
    dist = score_distribution(state, when=when, conditional=conditional)
    return distribution_table(dist, min_prob=min_prob)

def max_score_distribution_table(state, ns=None, max_n=None, when="after", *, conditional=True, min_prob=0.0):
    if ns is not None and max_n is not None:
        raise ValueError("Pass either ns or max_n, not both.")

    if ns is None:
        if max_n is None:
            raise ValueError("Pass either ns or max_n.")
        ns = range(1, max_n + 1)
    else:
        ns = list(ns)

    base_prob = score_distribution(state, when=when, conditional=conditional).astype(np.float64)

    total = base_prob.sum()
    if total <= 0:
        raise ValueError("Base score distribution has zero mass.")

    base_prob = base_prob / total

    scores = np.arange(len(base_prob), dtype=np.int64)
    out = pd.DataFrame({"score": scores})

    # tail_gt[x] = P(one-player score > x)
    tail_gt = np.zeros_like(base_prob)
    tail_gt[:-1] = np.cumsum(base_prob[:0:-1])[::-1]

    # tail_ge[x] = P(one-player score >= x)
    tail_ge = tail_gt + base_prob

    for n in ns:
        # P(max <= x) = P(all players <= x)
        #             = (1 - P(one player > x)) ** n
        #
        # Use log1p so that tiny right-tail probabilities do not get rounded away.
        log_cdf = n * np.log1p(-tail_gt)

        # P(max <= x-1) = P(all players < x)
        #                = P(all players <= x-1)
        #                = (1 - P(one player >= x)) ** n
        log_prev_cdf = n * np.log1p(-tail_ge)

        max_cdf = np.exp(log_cdf)

        # Stable version of exp(log_cdf) - exp(log_prev_cdf)
        max_prob = np.exp(log_cdf) * (-np.expm1(log_prev_cdf - log_cdf))

        max_prob = np.maximum(max_prob, 0.0)

        out[f"prob_n{n}"] = max_prob
        out[f"cdf_n{n}"] = max_cdf

    if min_prob > 0:
        prob_cols = [f"prob_n{n}" for n in ns]
        out = out[out[prob_cols].max(axis=1) >= min_prob].reset_index(drop=True)

    return out

def _reach_for_state(payload, row):
    return float(payload["reach_prob"][row]) if "reach_prob" in payload.files else 1.0

def upper_bonus_distribution(state, when="after", *, conditional=True):
    """
    Pseudo-box distribution for the 35-point upper bonus.

    before: bonus already awarded iff state.upper_total is capped at 63.
    after: future bonus is possible only if state.upper_total < 63.
    """
    when = when.lower()
    payload, row = get_state_row(state)
    dist = np.zeros(36, dtype=np.float64)

    if when in {"before", "past", "pre"}:
        points = UPPER_BONUS if state.upper_total >= UPPER_BONUS_THRESHOLD else 0
        dist[points] = 1.0
        if not conditional:
            dist *= _reach_for_state(payload, row)
        return dist

    if when in {"after", "future", "post"}:
        if state.upper_total >= UPPER_BONUS_THRESHOLD:
            dist[0] = 1.0
            return dist

        name = "p_top_bonus_after"
        if name not in payload.files:
            raise KeyError(f"Missing {name}. Run aggregate_properties.py backward-scalars.")
        p = float(payload[name][row])
        dist[0] = 1.0 - p
        dist[UPPER_BONUS] = p
        return dist

    raise ValueError("when must be 'before' or 'after'")

def yahtzee_bonus_distribution(state, when="after", *, conditional=True, as_points=True):
    """
    Pseudo-box distribution for extra +100 Yahtzee bonuses.

    Stored arrays are over number of extra Yahtzee bonuses, 0..12.
    If as_points=True, companion table/stats functions report values 0,100,...,1200.
    """
    when = when.lower()
    payload, row = get_state_row(state)

    if when in {"before", "past", "pre"}:
        name = "yahtzee_bonus_dist_before"
        if name not in payload.files:
            raise KeyError(f"Missing {name}. Run aggregate_properties.py forward-yahtzee-bonus-dist.")
        dist = payload[name][row].astype(np.float64)
        if conditional:
            reach = _reach_for_state(payload, row)
            dist = _normalize_distribution(dist, reach)[0]
        return dist

    if when in {"after", "future", "post"}:
        name = "yahtzee_bonus_dist_after"
        if name not in payload.files:
            raise KeyError(f"Missing {name}. Run aggregate_properties.py backward-yahtzee-bonus-dist.")
        return payload[name][row].astype(np.float64)

    raise ValueError("when must be 'before' or 'after'")

def box_distribution(state, category, when="after", *, conditional=True):
    """
    Return distribution for a real box or pseudo-box.

    Real boxes:
      before: P(reach state and box has score x), optionally normalized.
      after: future distribution if unfilled; all-zero if already filled.

    Pseudo-boxes:
      UpperBonus: distribution over 0 or 35 points.
      YahtzeeBonus: distribution over number of extra 100-point bonuses.
                    Use box_distribution_table for bonus-point values.
    """
    c = _resolve_category(category)
    if c == "UpperBonus":
        return upper_bonus_distribution(state, when=when, conditional=conditional)
    if c == "YahtzeeBonus":
        return yahtzee_bonus_distribution(state, when=when, conditional=conditional)

    when = when.lower()
    payload, row = get_state_row(state)

    if when in {"before", "past", "pre"}:
        name = box_before_name(c)
        if name not in payload.files:
            raise KeyError(f"Missing {name}. Run aggregate_properties.py forward-box-dist --category {CATEGORY_NAMES[c]}.")
        dist = payload[name][row].astype(np.float64)
        if conditional:
            reach = _reach_for_state(payload, row)
            return _normalize_distribution(dist, reach)[0]
        return dist

    if when in {"after", "future", "post"}:
        name = box_after_name(c)
        if name not in payload.files:
            raise KeyError(f"Missing {name}. Run aggregate_properties.py backward-box-dist --category {CATEGORY_NAMES[c]}.")
        return payload[name][row].astype(np.float64)

    raise ValueError("when must be 'before' or 'after'")

def _box_values(category):
    c = _resolve_category(category)
    if c == "YahtzeeBonus":
        # Stored bins are counts, but display values are bonus points.
        return 100 * np.arange(NUM_CATEGORIES, dtype=np.int64)
    return None

def box_distribution_stats(state, category, when="after", *, conditional=True):
    c = _resolve_category(category)
    dist = box_distribution(state, category, when=when, conditional=conditional)
    values = _box_values(category)
    stats = distribution_stats(dist, values=values)
    if c == "UpperBonus":
        stats["category"] = "UpperBonus"
        stats["filled_in_state"] = bool(state.upper_total >= UPPER_BONUS_THRESHOLD)
    elif c == "YahtzeeBonus":
        stats["category"] = "YahtzeeBonus"
        stats["filled_in_state"] = False
    else:
        stats["category"] = CATEGORY_NAMES[c]
        stats["filled_in_state"] = bool(state.filled_mask & (1 << c))
    stats["when"] = when
    return stats

def box_distribution_table(state, category, when="after", *, conditional=True, min_prob=1e-8):
    c = _resolve_category(category)
    dist = box_distribution(state, category, when=when, conditional=conditional)

    if c == "YahtzeeBonus":
        counts = np.arange(len(dist), dtype=np.int64)
        rows = []
        probs = _normalize_distribution(dist)[0] if conditional else dist
        for k, p in enumerate(probs):
            if p >= min_prob:
                rows.append({
                    "num_extra_yahtzees": int(k),
                    "score": int(100 * k),
                    "prob": float(p),
                })
        df = pd.DataFrame(rows)
        if len(df):
            df["cdf"] = df["prob"].cumsum()
        return df

    return distribution_table(dist, min_prob=min_prob)

def state_property_summary(state):
    """
    Compact table of scalar and distribution summaries for one reduced state.
    """
    payload, row = get_state_row(state)
    rows = []

    def add(name, value):
        rows.append({"property": name, "value": value})

    add("level", state_level(state))
    add("filled", ", ".join(categories_from_mask(state.filled_mask)))
    add("upper_total", int(state.upper_total))
    add("yahtzee_eligible", bool(state.yahtzee_eligible))

    for name in [
        "V",
        "reach_prob",
        "score_sum_before",
        "expected_score_before",
        "expected_score_after_check",
        "p_top_bonus_after",
    ]:
        if name in payload.files:
            add(name, float(payload[name][row]))

    if "score_dist_before" in payload.files:
        dist = payload["score_dist_before"][row]
        reach = _reach_for_state(payload, row)
        stats = distribution_stats(dist, mass=reach)
        add("score_dist_before_mass", stats["mass"])
        add("score_dist_before_mean_conditional", stats["mean"])
        add("score_dist_before_median_conditional", stats["median"])

    if "score_dist_after" in payload.files:
        stats = distribution_stats(payload["score_dist_after"][row])
        add("score_dist_after_mass", stats["mass"])
        add("score_dist_after_mean", stats["mean"])
        add("score_dist_after_median", stats["median"])

    if "p_top_bonus_after" in payload.files:
        add("upper_bonus_after_mean", box_distribution_stats(state, "UpperBonus", when="after")["mean"])

    if "yahtzee_bonus_dist_after" in payload.files:
        add("yahtzee_bonus_after_mean", box_distribution_stats(state, "YahtzeeBonus", when="after")["mean"])

    return pd.DataFrame(rows)

def all_box_summary(state, when="after", *, conditional=True, include_bonuses=True):
    rows = []
    for c, name in enumerate(CATEGORY_NAMES):
        arr_name = box_after_name(c) if when.lower() in {"after", "future", "post"} else box_before_name(c)
        payload, row = get_state_row(state)
        if arr_name not in payload.files:
            continue
        rows.append(box_distribution_stats(state, c, when=when, conditional=conditional))

    if include_bonuses:
        # These pseudo-box names are accepted by box_distribution_table/stats.
        for pseudo in ["UpperBonus", "YahtzeeBonus"]:
            try:
                rows.append(box_distribution_stats(state, pseudo, when=when, conditional=conditional))
            except KeyError:
                # If the relevant arrays have not been generated yet, omit the row.
                pass

    df = pd.DataFrame(rows)
    if len(df):
        cols = ["category", "when", "filled_in_state", "mass", "mean", "sd",
                "p_positive", "q05", "q25", "median", "q75", "q95",
                "min_nonzero", "max_nonzero", "n_nonzero"]
        return df[[c for c in cols if c in df.columns]]
    return df


# ## Inspect decisions for a specific state and roll

def inspect_roll(state, roll):
    '''
    roll can be a raw dice tuple/list like [1, 1, 3, 5, 6],
    or a dice_idx.
    '''
    dice_idx = int(roll) if isinstance(roll, (int, np.integer)) else dice_values_to_idx(roll)
    payload, row = get_state_row(state)

    keep_A = int(payload["decisions_A"][row, dice_idx])
    keep_B = int(payload["decisions_B"][row, dice_idx])
    cat_C = int(payload["decisions_C"][row, dice_idx])

    return pd.DataFrame([
        {
            "stage": "A: before first reroll",
            "roll": roll_label(dice_idx),
            "best_action": f"keep {keep_to_values(keep_A)}",
            "action_raw": ALL_KEEPS[keep_A],
            "EV": float(payload["ev_A"][row, dice_idx]),
        },
        {
            "stage": "B: before second reroll",
            "roll": roll_label(dice_idx),
            "best_action": f"keep {keep_to_values(keep_B)}",
            "action_raw": ALL_KEEPS[keep_B],
            "EV": float(payload["ev_B"][row, dice_idx]),
        },
        {
            "stage": "C: choose category",
            "roll": roll_label(dice_idx),
            "best_action": cat_name(cat_C),
            "action_raw": cat_C,
            "EV": float(payload["ev_C"][row, dice_idx]),
        },
    ])


# ## Rank first-keep or second-keep alternatives for a roll

def keep_alternatives(state, roll, stage="A"):
    dice_idx = int(roll) if isinstance(roll, (int, np.integer)) else dice_values_to_idx(roll)
    payload, row = get_state_row(state)

    if stage.upper() == "A":
        downstream = payload["ev_B"][row]
    elif stage.upper() == "B":
        downstream = payload["ev_C"][row]
    else:
        raise ValueError("stage must be 'A' or 'B'")

    rows = []
    for keep_idx in KEEPS_FOR_DICE[dice_idx]:
        finals, nums = REROLL_OUTCOMES[(dice_idx, int(keep_idx))]
        ev = sum(downstream[fi] * n for fi, n in zip(finals, nums)) / 7776.0
        rows.append({
            "keep_idx": int(keep_idx),
            "keep": keep_to_values(keep_idx),
            "keep_vec": ALL_KEEPS[int(keep_idx)],
            "EV": float(ev),
        })

    df = pd.DataFrame(rows).sort_values("EV", ascending=False).reset_index(drop=True)
    df["EV_gap_from_best"] = df["EV"].iloc[0] - df["EV"]
    return df


# ## Rank final category alternatives for a roll

def legal_categories_for_state_and_roll(state, dice_idx):
    return state.legal_categories_by_idx(dice_idx)

def category_alternatives(state, roll):
    dice_idx = int(roll) if isinstance(roll, (int, np.integer)) else dice_values_to_idx(roll)
    payload, row = get_state_row(state)

    # Load next-level V values by mask. Missing next states only happen at
    # terminal, where continuation value is zero.
    next_level = state_level(state) + 1
    V_next_by_mask = load_V_next(next_level)

    is_joker, categories = legal_categories_for_state_and_roll(state, dice_idx)
    score_row = JOKER_SCORE_ROWS[dice_idx] if is_joker else SCORE_ROWS[dice_idx]

    rows = []
    for c in categories:
        points = int(score_row[c])
        reward = points

        if c <= SIXES:
            new_upper = min(state.upper_total + points, UPPER_BONUS_THRESHOLD)
            if state.upper_total < UPPER_BONUS_THRESHOLD and state.upper_total + points >= UPPER_BONUS_THRESHOLD:
                reward += UPPER_BONUS
        else:
            new_upper = state.upper_total

        if is_joker and state.yahtzee_eligible:
            reward += EXTRA_YAHTZEE_BONUS

        if c == YAHTZEE and points == YAHTZEE_POINTS:
            new_eligible = True
        else:
            new_eligible = bool(state.yahtzee_eligible)

        new_mask = state.filled_mask | (1 << c)
        continuation = 0.0
        if new_mask in V_next_by_mask:
            continuation = float(V_next_by_mask[new_mask][new_upper, int(new_eligible)])

        rows.append({
            "category": cat_name(c),
            "category_idx": c,
            "is_joker": bool(is_joker),
            "score_points": points,
            "immediate_reward": reward,
            "new_upper": new_upper,
            "new_eligible": new_eligible,
            "continuation_EV": continuation,
            "total_EV": reward + continuation,
        })

    df = pd.DataFrame(rows).sort_values("total_EV", ascending=False).reset_index(drop=True)
    df["EV_gap_from_best"] = df["total_EV"].iloc[0] - df["total_EV"]
    return df


def stage_dice_probs(state, stage):
    """
    Probability of each dice state at a given within-turn stage under optimal play,
    conditional on starting the turn from this reduced state.

    A: after initial roll, before first keep
    B: after first reroll, before second keep
    C: after second reroll / final roll, before category choice
    """
    stage_key = stage.lower()
    payload, row = get_state_row(state)

    p_A = ALL_DICE_FREQS.astype(np.float64) / 7776.0

    if stage_key == "a":
        return p_A

    dec_A = payload["decisions_A"][row]

    p_B = np.zeros(len(ALL_DICE_STATES), dtype=np.float64)
    for d0 in range(len(ALL_DICE_STATES)):
        p0 = p_A[d0]
        if p0 == 0:
            continue

        keep_A = int(dec_A[d0])
        d1s, n1s = REROLL_OUTCOMES[(d0, keep_A)]
        for d1, n1 in zip(d1s, n1s):
            p_B[int(d1)] += p0 * (int(n1) / 7776.0)

    if stage_key == "b":
        return p_B

    dec_B = payload["decisions_B"][row]

    p_C = np.zeros(len(ALL_DICE_STATES), dtype=np.float64)
    for d1 in range(len(ALL_DICE_STATES)):
        p1 = p_B[d1]
        if p1 == 0:
            continue

        keep_B = int(dec_B[d1])
        d2s, n2s = REROLL_OUTCOMES[(d1, keep_B)]
        for d2, n2 in zip(d2s, n2s):
            p_C[int(d2)] += p1 * (int(n2) / 7776.0)

    if stage_key == "c":
        return p_C

    raise ValueError("stage must be one of: 'A', 'B', or 'C'")


def immediate_reward_for_category_choice(state, dice_idx, category):
    """
    Immediate reward from choosing category for this final roll:
    box score + possible upper bonus + possible extra Yahtzee bonus.
    """
    is_joker, _ = legal_categories_for_state_and_roll(state, dice_idx)
    score_row = JOKER_SCORE_ROWS[dice_idx] if is_joker else SCORE_ROWS[dice_idx]

    points = int(score_row[int(category)])
    reward = points

    if int(category) <= SIXES:
        if (
            state.upper_total < UPPER_BONUS_THRESHOLD
            and state.upper_total + points >= UPPER_BONUS_THRESHOLD
        ):
            reward += UPPER_BONUS

    if is_joker and state.yahtzee_eligible:
        reward += EXTRA_YAHTZEE_BONUS

    return reward


def all_roll_evs(state, stage="A", sort=True):
    """
    Return one row per unique dice combo for a given ReducedGameState.

    stage:
        "beginning" or "state" : EV before any roll, i.e. V(state)
                                 repeated only as summary-ish context
        "A"                   : EV after seeing the initial roll,
                                 before choosing first keep
        "B"                   : EV after seeing the second roll,
                                 before choosing second keep
        "C"                   : EV after seeing the final roll,
                                 before choosing category

    For A/B/C, the EV column is pulled directly from the stored value_iteration
    payload: ev_A, ev_B, or ev_C.

    The probability column is the probability of that dice state at the given
    stage under optimal play, conditional on starting from this reduced state.
    For stage A this is the raw initial-roll probability. For B/C it accounts
    for the optimal keep decisions from earlier stages.
    """
    stage_key = stage.lower()
    payload, row = get_state_row(state)

    if stage_key in {"beginning", "start", "state", "v"}:
        return pd.DataFrame([{
            "stage": "beginning",
            "state_EV": float(payload["V"][row]),
            "filled": categories_from_mask(state.filled_mask),
            "upper_total": state.upper_total,
            "yahtzee_eligible": bool(state.yahtzee_eligible),
        }])

    if stage_key == "a":
        evs = payload["ev_A"][row]
        decisions = payload["decisions_A"][row]
        action_type = "keep"
    elif stage_key == "b":
        evs = payload["ev_B"][row]
        decisions = payload["decisions_B"][row]
        action_type = "keep"
    elif stage_key == "c":
        evs = payload["ev_C"][row]
        decisions = payload["decisions_C"][row]
        action_type = "category"
    else:
        raise ValueError("stage must be one of: 'beginning', 'A', 'B', or 'C'")

    dice_probs = stage_dice_probs(state, stage_key)

    rows = []
    for dice_idx in range(len(ALL_DICE_STATES)):
        decision = int(decisions[dice_idx])

        if action_type == "keep":
            best_action = keep_to_values(decision)
            best_action_raw = ALL_KEEPS[decision]
        else:
            best_action = cat_name(decision)
            best_action_raw = decision

        row_data = {
            "stage": stage.upper(),
            "dice_idx": dice_idx,
            "roll": roll_label(dice_idx),
            "roll_vec": tuple(int(x) for x in ALL_DICE_STATES[dice_idx]),
            "roll_freq": int(ALL_DICE_FREQS[dice_idx]),
            "probability": float(dice_probs[dice_idx]),
            "best_action": best_action,
            "best_action_raw": best_action_raw,
            "EV": float(evs[dice_idx]),
        }

        if action_type == "category":
            row_data["immediate_reward"] = immediate_reward_for_category_choice(
                state, dice_idx, decision
            )

        rows.append(row_data)

    df = pd.DataFrame(rows)
    if sort:
        df = df.sort_values("EV", ascending=False).reset_index(drop=True)
    return df


def closest_first_keep_margins(state, n=20):
    rows = []
    for dice_idx in range(len(ALL_DICE_STATES)):
        alts = keep_alternatives(state, dice_idx, stage="A")
        if len(alts) < 2:
            continue
        rows.append({
            "roll": roll_label(dice_idx),
            "best_keep": alts.loc[0, "keep"],
            "best_EV": alts.loc[0, "EV"],
            "second_keep": alts.loc[1, "keep"],
            "second_EV": alts.loc[1, "EV"],
            "margin": alts.loc[0, "EV"] - alts.loc[1, "EV"],
        })
    return pd.DataFrame(rows).sort_values("margin").head(n).reset_index(drop=True)


# ## Final-outcome / round / matchup aggregate helpers

FINAL_OUTCOME_PATH = "data/final_outcome_dists/level_00/0000000000000.npz"

SCORE_BITS = 11
YAHTZEE_BITS = 4
SCORE_MASK = (1 << SCORE_BITS) - 1
YAHTZEE_MASK = (1 << YAHTZEE_BITS) - 1

FLAG_LARGE_STRAIGHT = 1 << 0
FLAG_SMALL_STRAIGHT = 1 << 1
FLAG_FULL_HOUSE     = 1 << 2
FLAG_FOUR_KIND      = 1 << 3
FLAG_THREE_KIND     = 1 << 4
FLAG_TOP_BONUS      = 1 << 5


def load_initial_final_outcome_df(path=FINAL_OUTCOME_PATH):
    with np.load(path) as f:
        offsets = f["offsets"]
        keys = f["keys"].astype(np.uint32)
        probs = f["probs"].astype(np.float64)

    start = int(offsets[0])
    end = int(offsets[1])

    keys = keys[start:end]
    probs = probs[start:end]

    score = keys & SCORE_MASK
    yahtzee_units = (keys >> SCORE_BITS) & YAHTZEE_MASK
    flags = keys >> (SCORE_BITS + YAHTZEE_BITS)

    df = pd.DataFrame({
        "score": score.astype(int),
        "probability": probs,
        "yahtzee_units": yahtzee_units.astype(int),
        "yahtzee_50": yahtzee_units >= 1,
        "extra_yahtzee_bonus": yahtzee_units >= 2,
        "num_extra_yahtzee_bonuses": np.maximum(yahtzee_units.astype(int) - 1, 0),
        "large_straight": (flags & FLAG_LARGE_STRAIGHT) != 0,
        "small_straight": (flags & FLAG_SMALL_STRAIGHT) != 0,
        "full_house": (flags & FLAG_FULL_HOUSE) != 0,
        "four_kind_nonzero": (flags & FLAG_FOUR_KIND) != 0,
        "three_kind_nonzero": (flags & FLAG_THREE_KIND) != 0,
        "top_bonus": (flags & FLAG_TOP_BONUS) != 0,
    })

    return df.sort_values("probability", ascending=False).reset_index(drop=True)

def score_prob_df(df, condition=None):
    if condition is None:
        d = df
    else:
        d = df[condition]

    return (
        d.groupby("score", as_index=False)["probability"]
        .sum()
        .sort_values("score")
    )


def plot_score_hist_with_condition(
    df,
    condition,
    label="condition",
    start=None,
    end=None,
):
    main = score_prob_df(df)
    sub = score_prob_df(df, condition)

    if start is not None:
        main = main[main["score"] >= start]
        sub = sub[sub["score"] >= start]
    if end is not None:
        main = main[main["score"] <= end]
        sub = sub[sub["score"] <= end]

    plt.bar(
        main["score"],
        main["probability"],
        width=1.0,
        alpha=0.35,
        label="all outcomes",
    )

    plt.bar(
        sub["score"],
        sub["probability"],
        width=1.0,
        alpha=0.85,
        label=label,
    )

    plt.legend()
    plt.show()


def category_by_round_df(
    state_properties_dir="data/state_properties",
    turn_kernels_dir="data/turn_kernels",
):
    rows = []

    for level in range(NUM_CATEGORIES):
        counts = np.zeros(NUM_CATEGORIES, dtype=np.float64)

        level_dir = os.path.join(state_properties_dir, f"level_{level:02d}")
        masks = sorted(
            int(filename[:-4], 2)
            for filename in os.listdir(level_dir)
            if filename.endswith(".npz")
        )

        for mask in masks:
            shard_path = os.path.join(
                state_properties_dir,
                f"level_{level:02d}",
                f"{mask:013b}.npz",
            )
            kernel_path = os.path.join(
                turn_kernels_dir,
                f"level_{level:02d}",
                f"{mask:013b}.npz",
            )

            with np.load(shard_path) as shard, np.load(kernel_path) as kernel:
                reach = shard["reach_prob"].astype(np.float64)

                offsets = kernel["offsets"]
                category_all = kernel["category"]
                numerator_all = kernel["numerator"].astype(np.float64)
                denom = float(kernel["denom"]) if "denom" in kernel.files else float(7776 ** 3)

                for row, row_reach in enumerate(reach):
                    if row_reach == 0:
                        continue

                    s = slice(int(offsets[row]), int(offsets[row + 1]))
                    cats = category_all[s].astype(int)
                    probs = numerator_all[s] / denom

                    np.add.at(counts, cats, row_reach * probs)

        for category, prob in enumerate(counts):
            rows.append({
                "round": level + 1,
                "category": category,
                "category_name": CATEGORY_NAMES[category],
                "probability": prob,
            })

    return pd.DataFrame(rows)


def box_value_by_round_df(
    state_properties_dir="data/state_properties",
    turn_kernels_dir="data/turn_kernels",
):
    rows = []

    for level in range(NUM_CATEGORIES):
        counts = {}

        level_dir = os.path.join(state_properties_dir, f"level_{level:02d}")
        masks = sorted(
            int(filename[:-4], 2)
            for filename in os.listdir(level_dir)
            if filename.endswith(".npz")
        )

        for mask in masks:
            shard_path = os.path.join(
                state_properties_dir,
                f"level_{level:02d}",
                f"{mask:013b}.npz",
            )
            kernel_path = os.path.join(
                turn_kernels_dir,
                f"level_{level:02d}",
                f"{mask:013b}.npz",
            )

            with np.load(shard_path) as shard, np.load(kernel_path) as kernel:
                reach = shard["reach_prob"].astype(np.float64)

                offsets = kernel["offsets"]
                category_all = kernel["category"].astype(int)
                box_points_all = kernel["box_points"].astype(int)
                numerator_all = kernel["numerator"].astype(np.float64)
                denom = float(kernel["denom"]) if "denom" in kernel.files else float(7776 ** 3)

                for row, row_reach in enumerate(reach):
                    if row_reach == 0:
                        continue

                    s = slice(int(offsets[row]), int(offsets[row + 1]))

                    cats = category_all[s]
                    box_points = box_points_all[s]
                    probs = row_reach * numerator_all[s] / denom

                    for cat, pts, prob in zip(cats, box_points, probs):
                        key = (level + 1, int(cat), int(pts))
                        counts[key] = counts.get(key, 0.0) + float(prob)

        for (round_num, category, box_points), prob in counts.items():
            rows.append({
                "round": round_num,
                "category": category,
                "category_name": CATEGORY_NAMES[category],
                "box_points": box_points,
                "probability": prob,
            })

    return (
        pd.DataFrame(rows)
        .sort_values(["round", "category", "box_points"])
        .reset_index(drop=True)
    )


def future_box_ev_given_unfilled_df(state_properties_dir="data/state_properties"):
    rows = []
    scores = np.arange(51)

    for level in range(NUM_CATEGORIES):
        level_dir = os.path.join(state_properties_dir, f"level_{level:02d}")
        masks = sorted(
            int(filename[:-4], 2)
            for filename in os.listdir(level_dir)
            if filename.endswith(".npz")
        )

        for category in range(NUM_CATEGORIES):
            dist_name = f"box_score_dist_after_{category:02d}"

            numerator = 0.0
            denominator = 0.0

            for mask in masks:
                if mask & (1 << category):
                    continue

                shard_path = os.path.join(
                    state_properties_dir,
                    f"level_{level:02d}",
                    f"{mask:013b}.npz",
                )

                with np.load(shard_path) as shard:
                    reach = shard["reach_prob"].astype(np.float64)
                    dist = shard[dist_name].astype(np.float64)

                row_ev = dist @ scores

                numerator += np.dot(reach, row_ev)
                denominator += reach.sum()

            rows.append({
                "round": level + 1,
                "category": category,
                "category_name": CATEGORY_NAMES[category],
                "unfilled_prob": denominator,
                "expected_value": numerator / denominator,
            })

    return pd.DataFrame(rows)


def yahtzee_bonus_ev_given_yahtzee_unfilled_df(state_properties_dir="data/state_properties"):
    rows = []
    bonus_counts = np.arange(13)
    yahtzee_category = CATEGORY_NAMES.index("Yahtzee")

    for level in range(NUM_CATEGORIES):
        level_dir = os.path.join(state_properties_dir, f"level_{level:02d}")
        masks = sorted(
            int(filename[:-4], 2)
            for filename in os.listdir(level_dir)
            if filename.endswith(".npz")
        )

        numerator = 0.0
        denominator = 0.0

        for mask in masks:
            if mask & (1 << yahtzee_category):
                continue

            shard_path = os.path.join(
                state_properties_dir,
                f"level_{level:02d}",
                f"{mask:013b}.npz",
            )

            with np.load(shard_path) as shard:
                reach = shard["reach_prob"].astype(np.float64)
                dist = shard["yahtzee_bonus_dist_after"].astype(np.float64)

            row_ev_bonus_count = dist @ bonus_counts

            numerator += np.dot(reach, 100 * row_ev_bonus_count)
            denominator += reach.sum()

        rows.append({
            "round": level + 1,
            "category_name": "YahtzeeBonus",
            "unfilled_prob": denominator,
            "expected_value": numerator / denominator,
        })

    return pd.DataFrame(rows)


def future_box_ev_with_yahtzee_bonus_pivot(state_properties_dir="data/state_properties"):
    box_df = future_box_ev_given_unfilled_df(state_properties_dir)
    bonus_df = yahtzee_bonus_ev_given_yahtzee_unfilled_df(state_properties_dir)

    box_pivot = box_df.pivot(
        index="round",
        columns="category_name",
        values="expected_value",
    )

    bonus_pivot = bonus_df.pivot(
        index="round",
        columns="category_name",
        values="expected_value",
    )

    return box_pivot.join(bonus_pivot)


def load_reduced_point_df():
    path = Path("data/reduced_point_dists/level_00/0000000000000.npz")

    with np.load(path) as f:
        offsets = f["offsets"]
        keys = f["keys"].astype(np.uint32)
        probs = f["probs"].astype(np.float64)

    # Start state should be row 0 in level_00.
    start = int(offsets[0])
    end = int(offsets[1])

    row_keys = keys[start:end]
    row_probs = probs[start:end]

    points = (row_keys & ((1 << 11) - 1)).astype(int)
    reduced_points = (row_keys >> 11).astype(int)

    return (
        pd.DataFrame({
            "points": points,
            "reduced_points": reduced_points,
            "probability": row_probs,
        })
        .sort_values(["reduced_points", "points"])
        .reset_index(drop=True)
    )

def reduced_point_matchup_table(df, max_reduced_points=None):
    """
    Entry [x, y] is:

        P(A actual score > B actual score)
        + 0.5 * P(A actual score == B actual score)

    conditional on:

        A reduced_points = x
        B reduced_points = y

    Assumes A and B are independent draws from the same distribution.

    If max_reduced_points is provided, only include rows/columns with
    reduced_points <= max_reduced_points.
    """
    cond = (
        df.groupby(["reduced_points", "points"], as_index=False)["probability"]
        .sum()
    )

    if max_reduced_points is not None:
        cond = cond[cond["reduced_points"] <= max_reduced_points].copy()

    totals = cond.groupby("reduced_points")["probability"].transform("sum")
    cond["conditional_probability"] = cond["probability"] / totals

    reduced_values = sorted(cond["reduced_points"].unique())

    out = pd.DataFrame(
        index=reduced_values,
        columns=reduced_values,
        dtype=float,
    )

    for a_rp in reduced_values:
        a = cond[cond["reduced_points"] == a_rp][
            ["points", "conditional_probability"]
        ]

        a_points = a["points"].to_numpy()
        a_probs = a["conditional_probability"].to_numpy()

        for b_rp in reduced_values:
            b = (
                cond[cond["reduced_points"] == b_rp][
                    ["points", "conditional_probability"]
                ]
                .sort_values("points")
                .reset_index(drop=True)
            )

            b_points = b["points"].to_numpy()
            b_probs = b["conditional_probability"].to_numpy()

            win_prob = 0.0

            for points, p_a in zip(a_points, a_probs):
                less_left = np.searchsorted(b_points, points, side="left")
                equal_right = np.searchsorted(b_points, points, side="right")

                p_b_less = b_probs[:less_left].sum()
                p_b_equal = b_probs[less_left:equal_right].sum()

                win_prob += p_a * (p_b_less + 0.5 * p_b_equal)

            out.loc[a_rp, b_rp] = win_prob

    out.index.name = "a_reduced_points"
    out.columns.name = "b_reduced_points"

    return out

def reduced_point_marginal(df):
    return (
        df.groupby("reduced_points", as_index=False)["probability"]
        .sum()
        .rename(columns={"probability": "p_reduced_points"})
        .sort_values("reduced_points")
        .reset_index(drop=True)
    )


def win_prob_given_more_reduced_points(df, matchup_table=None):
    """
    Computes:

        P(A actual points beats B actual points | A reduced_points > B reduced_points)

    Ties in actual points count as half a win.
    """
    if matchup_table is None:
        matchup_table = reduced_point_matchup_table(df)

    rp = reduced_point_marginal(df)

    p_by_rp = dict(
        zip(
            rp["reduced_points"].astype(int),
            rp["p_reduced_points"].astype(float),
        )
    )

    numerator = 0.0
    denominator = 0.0

    for a_rp in matchup_table.index:
        for b_rp in matchup_table.columns:
            if int(a_rp) <= int(b_rp):
                continue

            pair_prob = p_by_rp[int(a_rp)] * p_by_rp[int(b_rp)]
            win_prob = float(matchup_table.loc[a_rp, b_rp])

            numerator += pair_prob * win_prob
            denominator += pair_prob

    return numerator / denominator

def win_prob_given_reduced_point_diff(df, k, matchup_table=None):
    """
    Computes:

        P(A actual points beats B actual points | A reduced_points - B reduced_points = k)

    Ties in actual points count as half a win.
    """
    if matchup_table is None:
        matchup_table = reduced_point_matchup_table(df)

    rp = reduced_point_marginal(df)

    p_by_rp = dict(
        zip(
            rp["reduced_points"].astype(int),
            rp["p_reduced_points"].astype(float),
        )
    )

    k = int(k)

    numerator = 0.0
    denominator = 0.0

    for b_rp in matchup_table.columns:
        a_rp = int(b_rp) + k

        if a_rp not in matchup_table.index:
            continue

        pair_prob = p_by_rp[a_rp] * p_by_rp[int(b_rp)]
        win_prob = float(matchup_table.loc[a_rp, b_rp])

        numerator += pair_prob * win_prob
        denominator += pair_prob

    if denominator == 0:
        return np.nan

    return numerator / denominator
