"""Backward-induction value iteration over ReducedGameStates.

For each non-terminal state s, stores V(s) plus per-stage decisions and EVs:
  C: post-2nd reroll, pick a category.
  B: between 1st and 2nd reroll, pick a keep.
  A: before 1st reroll, pick a keep.
"No reroll" is encoded as keep == current dice (one outcome, numerator 7776).

Output is sharded by mask: data/state_properties/level_kk/<13-bit mask>.npz.
"""
import os
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
from tqdm import tqdm

from constants import (
    NUM_CATEGORIES, ONES, SIXES, THREE_KIND, YAHTZEE,
    UPPER_BONUS, UPPER_BONUS_THRESHOLD, EXTRA_YAHTZEE_BONUS, YAHTZEE_POINTS,
)
from precomputed import (
    NUM_DICE_STATES, ALL_DICE_FREQS, KEEPS_FOR_DICE, REROLL_OUTCOMES,
    SCORE_ROWS, JOKER_SCORE_ROWS, IS_YAHTZEE_T, YAHTZEE_FACE_T,
)
from state_properties import STATE_PROPERTIES_DIR, shard_path, save_shard


REDUCED_DIR = "data/reduced_states"

_ALL_DICE_FREQS_F = ALL_DICE_FREQS.astype(np.float64)
_DICE_RANGE = np.arange(NUM_DICE_STATES)
_UPPER_CAT_MASK = np.zeros(NUM_CATEGORIES, dtype=bool)
_UPPER_CAT_MASK[: SIXES + 1] = True
_TERMINAL_V = np.zeros((UPPER_BONUS_THRESHOLD + 1, 2), dtype=np.float32)


def _build_reroll_matrix():
    """Flatten REROLL_OUTCOMES into a (NUM_DK_PAIRS, NUM_DICE_STATES) dense matrix
    so stages A/B reduce to one matmul: ev_flat = ev_in @ M.T / 7776."""
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


def _build_mask_info(mask):
    """Precompute (legal, base, is_joker) tables that depend only on mask."""
    yahtzee_filled = bool(mask & (1 << YAHTZEE))
    open_upper = [c for c in range(ONES, SIXES + 1) if not (mask & (1 << c))]
    open_lower = [c for c in range(THREE_KIND, NUM_CATEGORIES) if not (mask & (1 << c))]
    unused = [c for c in range(NUM_CATEGORIES) if not (mask & (1 << c))]

    legal_2d = np.zeros((NUM_DICE_STATES, NUM_CATEGORIES), dtype=bool)
    base_2d = np.zeros((NUM_DICE_STATES, NUM_CATEGORIES), dtype=np.int32)
    is_joker = np.zeros(NUM_DICE_STATES, dtype=bool)
    for d in range(NUM_DICE_STATES):
        if IS_YAHTZEE_T[d] and yahtzee_filled:
            face = YAHTZEE_FACE_T[d]
            cats = (face,) if not (mask & (1 << face)) else (tuple(open_lower) or tuple(open_upper))
            is_joker[d] = True
            base_2d[d] = JOKER_SCORE_ROWS[d]
        else:
            cats = unused
            base_2d[d] = SCORE_ROWS[d]
        for c in cats:
            legal_2d[d, c] = True
    return legal_2d, base_2d, is_joker


def _stage_C(upper, eligible, legal_2d, base_2d, is_joker, V_for_cat):
    """Vectorized stage C for one (upper, eligible) state on a precomputed mask."""
    reward = base_2d.astype(np.float64)
    if upper < UPPER_BONUS_THRESHOLD:
        crossed = (upper + base_2d) >= UPPER_BONUS_THRESHOLD
        reward += (crossed & _UPPER_CAT_MASK[np.newaxis, :]) * float(UPPER_BONUS)
    if eligible:
        reward += is_joker[:, np.newaxis].astype(np.float64) * float(EXTRA_YAHTZEE_BONUS)

    new_upper = np.where(
        _UPPER_CAT_MASK[np.newaxis, :],
        np.minimum(upper + base_2d, UPPER_BONUS_THRESHOLD),
        upper,
    )
    new_eligible = np.full((NUM_DICE_STATES, NUM_CATEGORIES), int(eligible), dtype=np.int8)
    if not eligible:
        new_eligible[:, YAHTZEE] = (base_2d[:, YAHTZEE] == YAHTZEE_POINTS).astype(np.int8)

    V_next_2d = np.zeros((NUM_DICE_STATES, NUM_CATEGORIES))
    for c in range(NUM_CATEGORIES):
        V_next_2d[:, c] = V_for_cat[c][new_upper[:, c], new_eligible[:, c]]

    candidate = np.where(legal_2d, reward + V_next_2d, -np.inf)
    best_cat = candidate.argmax(axis=1)
    return best_cat.astype(np.uint8), candidate[_DICE_RANGE, best_cat]


def _stage_keep_batched(ev_in_batch):
    """ev_in_batch: (N, 252). Returns (decisions, ev_out) each (N, 252)."""
    N = ev_in_batch.shape[0]
    ev_flat = (ev_in_batch @ REROLL_MATRIX.T) / 7776.0
    decisions = np.empty((N, NUM_DICE_STATES), dtype=np.uint16)
    ev_out = np.empty((N, NUM_DICE_STATES))
    n_arange = np.arange(N)
    for d in range(NUM_DICE_STATES):
        seg = ev_flat[:, REROLL_OFFSETS[d]: REROLL_OFFSETS[d + 1]]
        local = seg.argmax(axis=1)
        decisions[:, d] = REROLL_PAIR_KEEPS[REROLL_OFFSETS[d] + local]
        ev_out[:, d] = seg[n_arange, local]
    return decisions, ev_out


def load_V_next(level):
    """Read all per-mask files in `level` into dict[mask] -> (64, 2) float32 array."""
    out = {}
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return out
    for fn in os.listdir(level_dir):
        if not fn.endswith(".npz"):
            continue
        mask = int(fn[:-4], 2)
        with np.load(os.path.join(level_dir, fn)) as p:
            arr = np.zeros((UPPER_BONUS_THRESHOLD + 1, 2), dtype=np.float32)
            arr[p["upper_total"], p["yahtzee_eligible"].astype(np.int8)] = p["V"]
        out[mask] = arr
    return out


def process_mask(level, mask, states, V_next):
    """Compute and write per-mask payload for all states sharing this mask."""
    ss = sorted(states, key=lambda s: (s.upper_total, s.yahtzee_eligible))
    N = len(ss)
    legal_2d, base_2d, is_joker = _build_mask_info(mask)
    V_for_cat = [V_next.get(mask | (1 << c), _TERMINAL_V) for c in range(NUM_CATEGORIES)]

    ev_C = np.empty((N, NUM_DICE_STATES))
    dec_C = np.empty((N, NUM_DICE_STATES), dtype=np.uint8)
    for i, s in enumerate(ss):
        dec_C[i], ev_C[i] = _stage_C(s.upper_total, s.yahtzee_eligible,
                                     legal_2d, base_2d, is_joker, V_for_cat)

    dec_B, ev_B = _stage_keep_batched(ev_C)
    dec_A, ev_A = _stage_keep_batched(ev_B)
    V = (ev_A @ _ALL_DICE_FREQS_F) / 7776.0

    save_shard(
        level, mask,
        merge=False,
        upper_total=np.array([s.upper_total for s in ss], dtype=np.uint8),
        yahtzee_eligible=np.array([s.yahtzee_eligible for s in ss], dtype=bool),
        V=V.astype(np.float32),
        decisions_A=dec_A,
        decisions_B=dec_B,
        decisions_C=dec_C,
        ev_A=ev_A.astype(np.float32),
        ev_B=ev_B.astype(np.float32),
        ev_C=ev_C.astype(np.float32),
    )


_WORKER_V_NEXT = None


def _worker_init(next_level):
    global _WORKER_V_NEXT
    _WORKER_V_NEXT = load_V_next(next_level)


def _worker_compute_mask(level, mask, states):
    process_mask(level, mask, states, _WORKER_V_NEXT)


def process_level(level, num_workers=None):
    if num_workers is None:
        num_workers = os.cpu_count()
    with open(os.path.join(REDUCED_DIR, f"level_{level:02d}.pkl"), "rb") as f:
        states = pickle.load(f)
    by_mask = {}
    for s in states:
        by_mask.setdefault(s.filled_mask, []).append(s)
    os.makedirs(os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}"), exist_ok=True)

    print(f"level {level:2d}: {len(states):,} states, {len(by_mask)} masks")
    with ProcessPoolExecutor(
        max_workers=num_workers,
        initializer=_worker_init,
        initargs=(level + 1,),
    ) as executor:
        futures = [
            executor.submit(_worker_compute_mask, level, mask, ss)
            for mask, ss in tqdm(by_mask.items())
        ]
        for fut in tqdm(as_completed(futures), total=len(futures)):
            fut.result()


def run_all(start_level=12, num_workers=None):
    for level in range(start_level, -1, -1):
        process_level(level, num_workers)
    with np.load(shard_path(0, 0)) as p:
        print(f"V(initial state) = {float(p['V'][0]):.4f}")


if __name__ == "__main__":
    run_all()