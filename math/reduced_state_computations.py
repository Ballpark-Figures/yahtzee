"""Enumerate every reachable ReducedGameState, one file per level.

Compared with state_computations.py: no per-mask sharding, no per-mask
output files, no on-disk merge. Each level's full set of reachable states
fits comfortably in RAM (the whole space is bounded by ~8192 * 64 * 2 = 1M).

For each level k -> k+1:
  1. Load level_k.pkl (a set of ReducedGameState).
  2. Split the set into ~num_workers chunks.
  3. Workers expand their chunks into successor sets.
  4. Parent unions all worker sets and writes level_{k+1}.pkl.
"""
import os
import pickle
from concurrent.futures import ProcessPoolExecutor

from tqdm import tqdm

from precomputed import NUM_DICE_STATES
from reduced_game_state import ReducedGameState


REDUCED_LEVEL_DIR = "data/reduced_states"


def get_level_path(level: int) -> str:
    return os.path.join(REDUCED_LEVEL_DIR, f"level_{level:02d}.pkl")


def _worker_expand(states):
    """Expand a list of states into the union of their successor states."""
    successors = set()
    for state in states:
        for dice_idx in range(NUM_DICE_STATES):
            is_joker, categories = state.legal_categories_by_idx(dice_idx)
            for cat in categories:
                _, new_state = state.fill_by_idx(cat, dice_idx, is_joker)
                successors.add(new_state)
    return successors


def _chunk(seq, num_chunks):
    """Split `seq` into roughly equal-sized lists."""
    n = len(seq)
    if num_chunks <= 0 or n == 0:
        return [list(seq)] if n else []
    size = (n + num_chunks - 1) // num_chunks
    return [seq[i:i + size] for i in range(0, n, size)]


def enumerate_reachable_reduced_states(num_workers: int = None, start_level: int = 0) -> None:
    if num_workers is None:
        num_workers = os.cpu_count()

    os.makedirs(REDUCED_LEVEL_DIR, exist_ok=True)

    # Seed level 0 if we're starting fresh.
    if start_level == 0:
        initial = ReducedGameState(filled_mask=0, upper_total=0, yahtzee_eligible=False)
        with open(get_level_path(0), "wb") as f:
            pickle.dump({initial}, f, protocol=pickle.HIGHEST_PROTOCOL)

    for level in range(start_level, 13):
        path_in = get_level_path(level)
        path_out = get_level_path(level + 1)

        if os.path.exists(path_out):
            print(f"level {level + 1:2d}: already exists, skipping")
            continue

        with open(path_in, "rb") as f:
            states = pickle.load(f)
        states_list = list(states)

        chunks = _chunk(states_list, num_workers)
        n = len(states_list)
        print(f"level {level:2d} -> {level + 1:2d}: {n:,} states in {len(chunks)} chunks")

        merged = set()
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            for result in tqdm(
                executor.map(_worker_expand, chunks),
                total=len(chunks),
                leave=False,
            ):
                merged |= result

        with open(path_out, "wb") as f:
            pickle.dump(merged, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"level {level + 1:2d}: {len(merged):,} states")


if __name__ == "__main__":
    enumerate_reachable_reduced_states()