"""Backward-induction value iteration over ReducedGameStates.

For each non-terminal state s, stores V(s) plus per-stage decisions and EVs:
  C: post-2nd reroll, pick a category.
  B: between 1st and 2nd reroll, pick a keep.
  A: before 1st reroll, pick a keep.
"No reroll" is encoded as keep == current dice (one outcome, numerator 7776).

Output is sharded by mask: data/values/level_kk/<13-bit mask>.pkl.
"""
import os
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
from tqdm import tqdm

from precomputed import (
    NUM_DICE_STATES, ALL_DICE_FREQS, KEEPS_FOR_DICE, REROLL_OUTCOMES,
)
from reduced_game_state import ReducedGameState


REDUCED_DIR = "data/reduced_states"
VALUES_DIR = "data/values"


def mask_path(level, mask):
    return os.path.join(VALUES_DIR, f"level_{level:02d}", f"{mask:013b}.pkl")


def _stage_keep(ev_in):
    """Stages A and B: max over keeps of expected next-stage EV."""
    decisions = np.empty(NUM_DICE_STATES, dtype=np.uint16)
    ev_out = np.empty(NUM_DICE_STATES)
    for d in range(NUM_DICE_STATES):
        best_v, best_k = -np.inf, 0
        for ki in KEEPS_FOR_DICE[d]:
            finals, nums = REROLL_OUTCOMES[(d, ki)]
            v = float(np.dot(nums, ev_in[list(finals)])) / 7776.0
            if v > best_v:
                best_v, best_k = v, ki
        ev_out[d], decisions[d] = best_v, best_k
    return decisions, ev_out


def compute_state(state, V_next):
    """Three-stage backward step. V_next: dict[ReducedGameState] -> V (0 if absent)."""
    ev_C = np.empty(NUM_DICE_STATES)
    dec_C = np.empty(NUM_DICE_STATES, dtype=np.uint8)
    for d in range(NUM_DICE_STATES):
        is_joker, cats = state.legal_categories_by_idx(d)
        best_v, best_c = -np.inf, 0
        for c in cats:
            reward, new_state = state.fill_by_idx(c, d, is_joker)
            v = reward + V_next.get(new_state, 0.0)
            if v > best_v:
                best_v, best_c = v, c
        ev_C[d], dec_C[d] = best_v, best_c
    dec_B, ev_B = _stage_keep(ev_C)
    dec_A, ev_A = _stage_keep(ev_B)
    V = float(np.dot(ALL_DICE_FREQS, ev_A)) / 7776.0
    return V, dec_A, dec_B, dec_C, ev_A, ev_B, ev_C


def load_V_next(level):
    """Read all per-mask files in `level` into one dict[state] -> V."""
    out = {}
    level_dir = os.path.join(VALUES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return out
    for fn in os.listdir(level_dir):
        if not fn.endswith(".pkl"):
            continue
        mask = int(fn[:-4], 2)
        with open(os.path.join(level_dir, fn), "rb") as f:
            p = pickle.load(f)
        for (u, e), v in zip(p["indices"], p["V"]):
            out[ReducedGameState(mask, u, e)] = float(v)
    return out


def process_mask(level, mask, states, V_next):
    """Compute and write per-mask payload for all states sharing this mask."""
    ss = sorted(states, key=lambda s: (s.upper_total, s.yahtzee_eligible))
    results = [compute_state(s, V_next) for s in ss]
    V, dA, dB, dC, eA, eB, eC = (np.array(x) for x in zip(*results))
    with open(mask_path(level, mask), "wb") as f:
        pickle.dump({
            "indices": [(s.upper_total, s.yahtzee_eligible) for s in ss],
            "V": V.astype(np.float32),
            "decisions_A": dA, "decisions_B": dB, "decisions_C": dC,
            "ev_A": eA.astype(np.float32),
            "ev_B": eB.astype(np.float32),
            "ev_C": eC.astype(np.float32),
        }, f, protocol=pickle.HIGHEST_PROTOCOL)


def _chunk(seq, n):
    seq = list(seq)
    size = (len(seq) + n - 1) // max(n, 1)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _worker_compute_masks(level, mask_groups):
    """One worker handles a chunk of (mask, states) pairs. V_next loaded once per worker."""
    V_next = load_V_next(level + 1)
    for mask, states in mask_groups:
        process_mask(level, mask, states, V_next)


def process_level(level, num_workers=None):
    if num_workers is None:
        num_workers = os.cpu_count()
    with open(os.path.join(REDUCED_DIR, f"level_{level:02d}.pkl"), "rb") as f:
        states = pickle.load(f)
    by_mask = {}
    for s in states:
        by_mask.setdefault(s.filled_mask, []).append(s)
    os.makedirs(os.path.join(VALUES_DIR, f"level_{level:02d}"), exist_ok=True)

    chunks = _chunk(list(by_mask.items()), num_workers)
    print(f"level {level:2d}: {len(states):,} states, {len(by_mask)} masks in {len(chunks)} chunks")
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(_worker_compute_masks, level, chunk) for chunk in chunks]
        for fut in tqdm(as_completed(futures), total=len(futures)):
            fut.result()


def run_all(start_level=12, num_workers=None):
    for level in range(start_level, -1, -1):
        process_level(level, num_workers)
    with open(mask_path(0, 0), "rb") as f:
        print(f"V(initial state) = {float(pickle.load(f)['V'][0]):.4f}")


if __name__ == "__main__":
    run_all()