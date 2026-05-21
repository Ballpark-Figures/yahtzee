"""Framework for per-state functionals built on top of the value-iteration policy.

Two drivers, both reading the optimal-policy arrays (decisions_A/B/C) from
shards and writing new properties alongside them:

- `run_backward(functionals)`: computes F(s) = E[functional of future | at s,
  play optimally]. Iterates levels 13 -> 0. Each `BackwardFunctional` supplies
  its terminal value and the stage-C combine logic; the driver handles the
  reroll-stage expectations and the initial-roll average.

- `run_forward(functionals)`: computes G(s) = joint weight at s tracking the
  functional of the past, under optimal play from the initial state. Iterates
  levels 0 -> 13. Each `ForwardFunctional` supplies its initial value and a
  stage-C shift; the driver handles the per-state propagation through both
  reroll stages and the accumulation into successor states.

Multiple functionals can be passed together; they share the per-mask step-info
computation and policy-array load but otherwise compute independently. Each
functional writes its values under a named array equal to `functional.name`.
"""
from abc import ABC, abstractmethod
import os
from typing import Sequence

import numpy as np
from tqdm import tqdm

from constants import (
    NUM_CATEGORIES, ONES, SIXES, YAHTZEE,
    UPPER_BONUS, UPPER_BONUS_THRESHOLD, EXTRA_YAHTZEE_BONUS, YAHTZEE_POINTS,
)
from precomputed import (
    NUM_DICE_STATES, ALL_DICE_FREQS, KEEPS_FOR_DICE, REROLL_OUTCOMES,
    SCORE_ROWS, JOKER_SCORE_ROWS, IS_YAHTZEE_T,
)
from state_properties import STATE_PROPERTIES_DIR, load_shard, save_shard


# ========================================================================
# Shared infrastructure
# ========================================================================

def _build_reroll_matrix():
    """REROLL_MATRIX[p, d'] = numerator (of 7776) for the (d, keep) pair at row p
    transitioning to dice-state d'. Same construction as value_iteration."""
    num_dk = sum(len(KEEPS_FOR_DICE[d]) for d in range(NUM_DICE_STATES))
    M = np.zeros((num_dk, NUM_DICE_STATES), dtype=np.float64)
    offsets = np.zeros(NUM_DICE_STATES + 1, dtype=np.int32)
    pair_keeps = np.zeros(num_dk, dtype=np.uint16)
    idx = 0
    for d in range(NUM_DICE_STATES):
        offsets[d] = idx
        for ki in KEEPS_FOR_DICE[d]:
            finals, nums = REROLL_OUTCOMES[(d, ki)]
            for fi, n in zip(finals, nums):
                M[idx, fi] = n
            pair_keeps[idx] = ki
            idx += 1
    offsets[-1] = idx
    return M, offsets, pair_keeps


REROLL_MATRIX, REROLL_OFFSETS, REROLL_PAIR_KEEPS = _build_reroll_matrix()
NUM_DK_PAIRS = REROLL_MATRIX.shape[0]


def _build_pair_table():
    """PAIR_TABLE[d, k] = row in REROLL_MATRIX for (dice d, keep k), or -1."""
    num_keeps = int(REROLL_PAIR_KEEPS.max()) + 1
    table = np.full((NUM_DICE_STATES, num_keeps), -1, dtype=np.int32)
    for d in range(NUM_DICE_STATES):
        for local, k in enumerate(KEEPS_FOR_DICE[d]):
            table[d, k] = REROLL_OFFSETS[d] + local
    return table


PAIR_TABLE = _build_pair_table()
ROLL_PROBS = ALL_DICE_FREQS.astype(np.float64) / 7776.0

SCORE_TABLE = np.array(SCORE_ROWS, dtype=np.int16)
JOKER_TABLE = np.array(JOKER_SCORE_ROWS, dtype=np.int16)
IS_YAHTZEE_ARR = np.array(IS_YAHTZEE_T, dtype=bool)


# ========================================================================
# Step info: per-(state, dice) transition info under stage-C policy
# ========================================================================

def compute_step_info(mask, upper_arr, eligible_arr, dec_C):
    """Compute per-(state, dice) info under the stage-C policy for one shard.

    All returned arrays have shape (N, 252) where N = len(upper_arr).
    """
    N = upper_arr.shape[0]
    yahtzee_filled = bool(mask & (1 << YAHTZEE))

    is_joker_d = IS_YAHTZEE_ARR & yahtzee_filled  # (252,)
    is_joker = np.broadcast_to(is_joker_d[None, :], (N, NUM_DICE_STATES)).copy()

    d_idx = np.arange(NUM_DICE_STATES)[None, :]
    cat = dec_C
    points_n = SCORE_TABLE[d_idx, cat]
    points_j = JOKER_TABLE[d_idx, cat]
    points = np.where(is_joker, points_j, points_n).astype(np.int16)

    is_upper = cat <= SIXES
    upper_2d = upper_arr[:, None].astype(np.int32)

    crossed = is_upper & (upper_2d < UPPER_BONUS_THRESHOLD) & (upper_2d + points >= UPPER_BONUS_THRESHOLD)

    eligible_2d = eligible_arr[:, None]
    earned_eyb = is_joker & eligible_2d

    new_upper = np.where(is_upper, np.minimum(upper_2d + points, UPPER_BONUS_THRESHOLD), upper_2d).astype(np.uint8)
    new_eligible = (eligible_2d | ((cat == YAHTZEE) & (points == YAHTZEE_POINTS))).astype(bool)

    immediate_reward = points.astype(np.int32) + crossed * UPPER_BONUS + earned_eyb * EXTRA_YAHTZEE_BONUS

    return {
        "category": cat,
        "is_joker": is_joker,
        "points": points,
        "is_upper": is_upper,
        "crossed_upper_bonus": crossed,
        "earned_eyb": earned_eyb,
        "new_upper": new_upper,
        "new_eligible": new_eligible,
        "immediate_reward": immediate_reward,
    }


def _flat_size(shape):
    return 1 if len(shape) == 0 else int(np.prod(shape))


def _list_shards(level):
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []
    out = []
    for fn in os.listdir(level_dir):
        if fn.endswith(".npz"):
            out.append((int(fn[:-4], 2), os.path.join(level_dir, fn)))
    return out


# ========================================================================
# Backward DP
# ========================================================================

class BackwardFunctional(ABC):
    """A property of the future, under optimal play, computed by backward DP."""

    name: str = "<unset>"
    value_shape: tuple = ()
    value_dtype: np.dtype = np.float32

    @abstractmethod
    def terminal_value(self, upper_total: int, yahtzee_eligible: bool) -> np.ndarray:
        """Value at a terminal state. Shape: value_shape."""

    @abstractmethod
    def stage_C(self, step_info, future_at_succ, s_idx, d_idx) -> np.ndarray:
        """Compute F_C for a batch of (s, d) pairs sharing one chosen category.

        Args:
            step_info: dict of (N, 252) arrays from compute_step_info.
            future_at_succ: (M, *value_shape) F-values at the chosen successor.
            s_idx, d_idx: (M,) selectors of the batched pairs.

        Returns:
            (M, *value_shape) F_C values.
        """

    def terminal_table(self):
        """Cached terminal-value lookup table, shape (64, 2, *value_shape)."""
        table = np.zeros((UPPER_BONUS_THRESHOLD + 1, 2) + self.value_shape, dtype=self.value_dtype)
        for u in range(UPPER_BONUS_THRESHOLD + 1):
            for e_idx, e in enumerate((False, True)):
                table[u, e_idx] = self.terminal_value(u, e)
        return table


def _stage_keep_expectation_backward(F_in, dec_keep, value_shape):
    """F_out[s, d] = E_{d'} F_in[s, d'] | keep = dec_keep[s, d].

    F_in shape: (N, 252, *value_shape). Returns same shape.
    """
    N = F_in.shape[0]
    L = _flat_size(value_shape)

    if len(value_shape) == 0:
        F_flat = (F_in @ REROLL_MATRIX.T) / 7776.0   # (N, num_dk)
    else:
        F_in_flat = F_in.reshape(N, NUM_DICE_STATES, L)
        F_flat = np.einsum('ndl,kd->nkl', F_in_flat, REROLL_MATRIX) / 7776.0
        F_flat = F_flat.reshape((N, NUM_DK_PAIRS) + value_shape)

    d_arr = np.arange(NUM_DICE_STATES)[None, :]
    pair_idx_2d = PAIR_TABLE[d_arr, dec_keep]    # (N, 252)
    s_arr = np.arange(N)[:, None]
    return F_flat[s_arr, pair_idx_2d]


def _compute_backward_at_mask(functionals, mask, shard, step_info, F_next_by_name):
    """Compute F values for each functional at every state in one shard."""
    N = shard["decisions_A"].shape[0]
    dec_A = shard["decisions_A"]
    dec_B = shard["decisions_B"]
    cat_arr = step_info["category"]

    updates = {}
    for f in functionals:
        vshape = f.value_shape
        F_C = np.zeros((N, NUM_DICE_STATES) + vshape, dtype=f.value_dtype)
        terminal_tbl = f.terminal_table()
        F_next = F_next_by_name[f.name]

        for c in range(NUM_CATEGORIES):
            sel = cat_arr == c
            if not sel.any():
                continue
            s_idx, d_idx = np.where(sel)
            succ_mask = mask | (1 << c)
            future_table = F_next.get(succ_mask, terminal_tbl)
            nu = step_info["new_upper"][s_idx, d_idx]
            ne = step_info["new_eligible"][s_idx, d_idx].astype(np.int8)
            future_at_succ = future_table[nu, ne].astype(f.value_dtype)
            F_C[s_idx, d_idx] = f.stage_C(step_info, future_at_succ, s_idx, d_idx)

        F_B = _stage_keep_expectation_backward(F_C, dec_B, vshape)
        F_A = _stage_keep_expectation_backward(F_B, dec_A, vshape)

        if len(vshape) == 0:
            F = F_A @ ROLL_PROBS
        else:
            L = _flat_size(vshape)
            F_flat = np.tensordot(F_A.reshape(N, NUM_DICE_STATES, L), ROLL_PROBS, axes=([1], [0]))
            F = F_flat.reshape((N,) + vshape)
        updates[f.name] = F.astype(f.value_dtype)
    return updates


def _load_F_next(name, level, value_shape, value_dtype):
    """For each mask at `level` that has the named array, build (64, 2, *vshape)."""
    out = {}
    table_shape = (UPPER_BONUS_THRESHOLD + 1, 2) + value_shape
    for mask, path in _list_shards(level):
        with np.load(path) as p:
            if name not in p.files:
                continue
            arr = np.zeros(table_shape, dtype=value_dtype)
            arr[p["upper_total"], p["yahtzee_eligible"].astype(np.int8)] = p[name]
        out[mask] = arr
    return out


def run_backward(functionals: Sequence[BackwardFunctional], show_progress: bool = True):
    """Compute each functional via backward DP, levels 13 -> 0. Multi-functional
    runs are batched: all functionals share the per-mask step-info computation.
    """
    for level in range(13, -1, -1):
        shards = _list_shards(level)
        if not shards:
            print(f"level {level:2d}: no shards present, skipping")
            continue

        F_next_by_name = {f.name: _load_F_next(f.name, level + 1, f.value_shape, f.value_dtype)
                          for f in functionals}

        iterator = tqdm(shards, desc=f"backward L{level:02d}") if show_progress else shards
        for mask, _ in iterator:
            with load_shard(level, mask) as shard:
                upper = shard["upper_total"]
                eligible = shard["yahtzee_eligible"]
                dec_C = shard["decisions_C"]
                shard_dict = {
                    "upper_total": upper, "yahtzee_eligible": eligible,
                    "decisions_A": shard["decisions_A"],
                    "decisions_B": shard["decisions_B"],
                    "decisions_C": dec_C,
                }
            step_info = compute_step_info(mask, upper, eligible, dec_C)
            updates = _compute_backward_at_mask(functionals, mask, shard_dict, step_info, F_next_by_name)
            save_shard(level, mask, merge=True, **updates)


# ========================================================================
# Forward DP
# ========================================================================

class ForwardFunctional(ABC):
    """A property of the past, under optimal play, computed by forward DP.

    Values are interpreted JOINTLY with the probability of reaching the state:
    G(s) for a distribution-valued functional is the unnormalized distribution
    such that G(s).sum() == P(reach s under optimal play). Caller normalizes if
    a conditional distribution is wanted.
    """

    name: str = "<unset>"
    value_shape: tuple = ()
    value_dtype: np.dtype = np.float32

    @abstractmethod
    def initial_value(self) -> np.ndarray:
        """Value at the initial state (level 0, mask 0, upper 0, eligible False)."""

    @abstractmethod
    def stage_C(self, step_info, G_C_sel, s_idx, d_idx) -> np.ndarray:
        """Apply the stage-C step shift to a batch of (s, d) values heading to
        the same chosen category.

        Args:
            step_info: per-(s, d) info from compute_step_info.
            G_C_sel: (M, *value_shape) values to be transformed.
            s_idx, d_idx: (M,) selectors.

        Returns:
            (M, *value_shape) values to accumulate at the successor state.
        """


def _stage_keep_propagation_forward(G_in, dec_keep, value_shape):
    """G_out[s, d'] = sum_d G_in[s, d] * P(d -> d' | keep = dec_keep[s, d]).

    G_in shape: (N, 252, *value_shape). Returns same shape.
    """
    N = G_in.shape[0]
    L = _flat_size(value_shape)

    d_arr = np.arange(NUM_DICE_STATES)[None, :]
    pair_idx_2d = PAIR_TABLE[d_arr, dec_keep]  # (N, 252)

    # Chunked over states to keep M_rows ((chunk, 252, 252) float64) bounded.
    CHUNK = 32

    if len(value_shape) == 0:
        G_in_flat = G_in.reshape(N, NUM_DICE_STATES)
        G_out_flat = np.empty_like(G_in_flat, dtype=np.float64)
        for s0 in range(0, N, CHUNK):
            s1 = min(s0 + CHUNK, N)
            M_rows = REROLL_MATRIX[pair_idx_2d[s0:s1]]   # (chunk, 252, 252)
            G_out_flat[s0:s1] = np.einsum('sdq,sd->sq', M_rows, G_in_flat[s0:s1])
        return (G_out_flat / 7776.0).astype(G_in.dtype).reshape(G_in.shape)
    else:
        G_in_flat = G_in.reshape(N, NUM_DICE_STATES, L)
        G_out_flat = np.empty_like(G_in_flat, dtype=np.float64)
        for s0 in range(0, N, CHUNK):
            s1 = min(s0 + CHUNK, N)
            M_rows = REROLL_MATRIX[pair_idx_2d[s0:s1]]
            G_out_flat[s0:s1] = np.einsum('sdq,sdl->sql', M_rows, G_in_flat[s0:s1])
        G_out_flat = G_out_flat / 7776.0
        return G_out_flat.astype(G_in.dtype).reshape((N, NUM_DICE_STATES) + value_shape)


def _compute_G_C_for_mask(f, shard):
    """Compute G_C[s, d] for all (s, d) in one shard, for one functional."""
    G_s = shard[f.name]   # (N, *value_shape)
    N = G_s.shape[0]
    vshape = f.value_shape
    L = _flat_size(vshape)

    # G_A[s, d] = G_s[s] * freq(d) / 7776
    if len(vshape) == 0:
        G_A = G_s[:, None] * ROLL_PROBS[None, :]   # (N, 252)
    else:
        G_s_flat = G_s.reshape(N, L)
        G_A_flat = G_s_flat[:, None, :] * ROLL_PROBS[None, :, None]   # (N, 252, L)
        G_A = G_A_flat.reshape((N, NUM_DICE_STATES) + vshape)

    dec_A = shard["decisions_A"]
    dec_B = shard["decisions_B"]
    G_B = _stage_keep_propagation_forward(G_A, dec_A, vshape)
    G_C = _stage_keep_propagation_forward(G_B, dec_B, vshape)
    return G_C


def run_forward(functionals: Sequence[ForwardFunctional], show_progress: bool = True):
    """Compute each functional via forward DP, levels 0 -> 13. Initializes the
    level-0 shard with each functional's `initial_value`.
    """
    # Seed level 0 (single state: mask=0, upper=0, eligible=False).
    with load_shard(0, 0) as shard0:
        N0 = shard0["upper_total"].shape[0]
    seeds = {}
    for f in functionals:
        arr = np.zeros((N0,) + f.value_shape, dtype=f.value_dtype)
        # Only the row at (upper=0, eligible=False) should get the initial value.
        with load_shard(0, 0) as shard0:
            ups = shard0["upper_total"]
            elig = shard0["yahtzee_eligible"]
        rows = np.where((ups == 0) & (~elig))[0]
        for r in rows:
            arr[r] = f.initial_value()
        seeds[f.name] = arr
    save_shard(0, 0, merge=True, **seeds)

    for level in range(13):
        shards = _list_shards(level)
        if not shards:
            print(f"level {level:2d}: no shards present, stopping forward pass")
            break
        next_shards_list = _list_shards(level + 1)
        if not next_shards_list:
            print(f"level {level + 1:2d}: no shards present, stopping forward pass")
            break

        # Pre-allocate accumulators for level+1, keyed by mask.
        next_shards = dict(next_shards_list)
        # For each next-level mask, we'll write (64, 2, *vshape) accumulators
        # and then place them into the rows of that mask's shard.
        accumulators = {}  # (next_mask, f.name) -> (64, 2, *vshape) float64
        for nm in next_shards:
            for f in functionals:
                shape = (UPPER_BONUS_THRESHOLD + 1, 2) + f.value_shape
                accumulators[(nm, f.name)] = np.zeros(shape, dtype=np.float64)

        iterator = tqdm(shards, desc=f"forward L{level:02d}") if show_progress else shards
        for mask, _ in iterator:
            with load_shard(level, mask) as shard:
                upper = shard["upper_total"]
                eligible = shard["yahtzee_eligible"]
                dec_C = shard["decisions_C"]
                shard_dict = {
                    "upper_total": upper, "yahtzee_eligible": eligible,
                    "decisions_A": shard["decisions_A"],
                    "decisions_B": shard["decisions_B"],
                    "decisions_C": dec_C,
                }
                for f in functionals:
                    shard_dict[f.name] = shard[f.name]
            step_info = compute_step_info(mask, upper, eligible, dec_C)

            for f in functionals:
                G_C = _compute_G_C_for_mask(f, shard_dict)   # (N, 252, *vshape)
                cat_arr = step_info["category"]
                for c in range(NUM_CATEGORIES):
                    sel = cat_arr == c
                    if not sel.any():
                        continue
                    s_idx, d_idx = np.where(sel)
                    next_mask = mask | (1 << c)
                    nu = step_info["new_upper"][s_idx, d_idx]
                    ne = step_info["new_eligible"][s_idx, d_idx].astype(np.int8)
                    G_C_sel = G_C[s_idx, d_idx].astype(f.value_dtype)
                    shifted = f.stage_C(step_info, G_C_sel, s_idx, d_idx)
                    acc = accumulators[(next_mask, f.name)]
                    np.add.at(acc, (nu, ne), shifted.astype(np.float64))

        # Place the accumulators back into the level+1 shards.
        for nm, _ in next_shards.items():
            with load_shard(level + 1, nm) as next_shard:
                ups = next_shard["upper_total"]
                elig = next_shard["yahtzee_eligible"]
            updates = {}
            for f in functionals:
                acc = accumulators[(nm, f.name)]
                updates[f.name] = acc[ups, elig.astype(np.int8)].astype(f.value_dtype)
            save_shard(level + 1, nm, merge=True, **updates)


# ========================================================================
# Helper: per-row shift (used by several functionals)
# ========================================================================

def shift_right_per_row(arr_2d, shifts):
    """For each row, shift right by shifts[i]; fill with zeros.

    arr_2d shape (M, L). shifts shape (M,) non-negative integers.
    Returns (M, L) array with result[i, k] = arr_2d[i, k - shifts[i]] (or 0).
    """
    M, L = arr_2d.shape
    j = np.arange(L)[None, :] - shifts[:, None]
    valid = j >= 0
    safe_j = np.where(valid, j, 0)
    return np.where(valid, arr_2d[np.arange(M)[:, None], safe_j], 0)