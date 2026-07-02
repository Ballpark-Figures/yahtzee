"""Count reachable ReducedGameState positions (the SECOND-reduction format).

This is the "second reduction" from scene 05: a position is identified by
(filled_mask, upper_total capped at 63, yahtzee_eligible bit) -- top score only
matters below 63, the bottom-section total is dropped, and the Yahtzee count
collapses to a single eligibility bit. That is `ReducedGameState`
(math/reduced_game_state.py), the solver's actual state space.

It COUNTS what's already on disk -- one row per ReducedGameState in the
`data/state_properties/level_NN/<mask>.npz` shards (each shard's `upper_total`
array has one entry per state). No unpickling, no game math recomputed.

Reports, with the same transform as Blank A (minus terminal, x756):
  * states per level (0..13)
  * non-terminal total (levels 0..12)
  * non-terminal total x 756                   <- the scene-05 Blank C figure

Run from the math/ project dir with its venv:
    cd math
    .venv/bin/python count_reduced_states.py
"""
import os

import numpy as np

STATE_PROPERTIES_DIR = "data/state_properties"
NUM_CATEGORIES = 13          # levels 0..13; level 13 = terminal (all boxes filled)
TURN_SITUATIONS = 756        # 252 x 3 rolls; converts board positions -> "positions"


def count_level(level: int):
    """Number of ReducedGameStates at `level`, or None if the shards are absent."""
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return None
    shard_files = [f for f in os.listdir(level_dir) if f.endswith(".npz")]
    if not shard_files:
        return None
    total = 0
    for fn in shard_files:
        with np.load(os.path.join(level_dir, fn)) as shard:
            total += int(shard["upper_total"].shape[0])
    return total


def main() -> None:
    counts = {level: count_level(level) for level in range(NUM_CATEGORIES + 1)}

    print("ReducedGameStates (second-reduction positions) per level:")
    for level in range(NUM_CATEGORIES + 1):
        c = counts[level]
        tag = " (terminal)" if level == NUM_CATEGORIES else ""
        print(f"  level {level:2d}: {'MISSING' if c is None else format(c, ',')}{tag}")

    missing = [l for l in range(NUM_CATEGORIES) if counts[l] is None]
    if missing:
        print(f"\nMISSING levels {missing} (need 0..12). state_properties shards absent.")
        return

    non_terminal = sum(counts[l] for l in range(NUM_CATEGORIES))  # levels 0..12
    print(f"\nnon-terminal states (levels 0..12): {non_terminal:,}")
    print(f"x {TURN_SITUATIONS}  ->  Blank C (second reduction): {non_terminal * TURN_SITUATIONS:,}")

    if counts[NUM_CATEGORIES] is not None:
        grand = non_terminal + counts[NUM_CATEGORIES]
        print(
            f"\n(for reference -- terminal level 13: {counts[NUM_CATEGORIES]:,}; "
            f"grand total incl terminal: {grand:,})"
        )


if __name__ == "__main__":
    main()
