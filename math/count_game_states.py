"""Count reachable GameState positions (the FIRST-reduction format) per level.

This is the "first reduction" from scene 05: a position is identified by
(filled_mask, upper_total, lower_total, num_yahtzees) -- i.e. which boxes are
filled, the top-section score, the bottom-section score, and the number of
Yahtzees. That is exactly `GameState` (math/game_state.py), enumerated by
`state_computations.py` into `data/state_levels/`.

It just COUNTS what `state_computations.py` already wrote -- it does not
recompute any game math. It handles either on-disk layout:
  * sharded per-mask:  data/state_levels/level_NN/<13-bit-mask>.pkl
  * one-file-per-level: data/state_levels/level_N.pkl

Reports, matching scene 01's arc (385,647,100,272 -> minus terminal -> x756):
  * states per level (0..13)
  * non-terminal total (levels 0..12)         <- game not yet over
  * non-terminal total x 756                   <- the scene-05 Blank A figure

Run from the math/ project dir with its venv, e.g.:
    cd math
    .venv/bin/python count_game_states.py

If it reports MISSING levels, the enumeration isn't fully on disk here; rebuild
it first with `.venv/bin/python state_computations.py` (heavy -- multiprocessing
BFS, many GB of pickles), then re-run this counter.
"""
import os
import pickle

# Import so unpickling can reconstruct GameState (via its __reduce__).
# NB: game_state -> precomputed loads data/ pickles at import time, so this must
# run from the math/ dir with the solver data present (same contract as the
# rest of the pipeline / state_explorer).
from game_state import GameState  # noqa: F401  (needed for unpickling)

LEVEL_DIR = "data/state_levels"
NUM_CATEGORIES = 13          # levels 0..13; level 13 = terminal (all boxes filled)
TURN_SITUATIONS = 756        # 252 x 3 rolls; converts board positions -> "positions"


def count_level(level: int):
    """Number of GameStates at `level`, or None if not on disk in either layout."""
    shard_dir = os.path.join(LEVEL_DIR, f"level_{level:02d}")
    if os.path.isdir(shard_dir):
        shard_files = [f for f in os.listdir(shard_dir) if f.endswith(".pkl")]
        if shard_files:
            total = 0
            for fn in shard_files:
                with open(os.path.join(shard_dir, fn), "rb") as f:
                    total += len(pickle.load(f))
            return total

    loose = os.path.join(LEVEL_DIR, f"level_{level}.pkl")
    if os.path.exists(loose):
        with open(loose, "rb") as f:
            return len(pickle.load(f))

    return None


def main() -> None:
    counts = {level: count_level(level) for level in range(NUM_CATEGORIES + 1)}

    print("GameStates (first-reduction positions) per level:")
    for level in range(NUM_CATEGORIES + 1):
        c = counts[level]
        tag = " (terminal)" if level == NUM_CATEGORIES else ""
        print(f"  level {level:2d}: {'MISSING' if c is None else format(c, ',')}{tag}")

    missing = [l for l in range(NUM_CATEGORIES) if counts[l] is None]
    if missing:
        print(
            f"\nMISSING levels {missing} (need 0..12). The enumeration isn't fully "
            "on disk here.\nRebuild with `.venv/bin/python state_computations.py`, "
            "then re-run this counter."
        )
        return

    non_terminal = sum(counts[l] for l in range(NUM_CATEGORIES))  # levels 0..12
    print(f"\nnon-terminal states (levels 0..12): {non_terminal:,}")
    print(f"x {TURN_SITUATIONS}  ->  Blank A (first reduction): {non_terminal * TURN_SITUATIONS:,}")

    if counts[NUM_CATEGORIES] is not None:
        grand = non_terminal + counts[NUM_CATEGORIES]
        print(
            f"\n(for reference -- terminal level 13: {counts[NUM_CATEGORIES]:,}; "
            f"grand total incl terminal: {grand:,})"
        )


if __name__ == "__main__":
    main()
