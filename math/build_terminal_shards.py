"""
Create terminal level-13 state_properties shards.

Input:
    data/reduced_states/level_13.pkl

Output:
    data/state_properties/level_13/1111111111111.npz

Terminal shards have no strategy arrays, because there is no turn to play.
They contain:

    upper_total
    yahtzee_eligible
    V

with V = 0 for every terminal reduced state.

Run from project root:

    python build_terminal_shards.py
"""

from __future__ import annotations

import os
import pickle

import numpy as np

from constants import NUM_CATEGORIES
from reduced_state_computations import get_level_path
from state_properties import save_shard


TERMINAL_LEVEL = NUM_CATEGORIES
FULL_MASK = (1 << NUM_CATEGORIES) - 1


def main() -> None:
    path = get_level_path(TERMINAL_LEVEL)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing {path}. Run reduced_state_computations.py first."
        )

    with open(path, "rb") as f:
        states = pickle.load(f)

    terminal_states = [s for s in states if s.filled_mask == FULL_MASK]

    if len(terminal_states) != len(states):
        bad = len(states) - len(terminal_states)
        raise ValueError(
            f"Expected all level-{TERMINAL_LEVEL} states to have full mask; "
            f"found {bad} nonterminal states."
        )

    terminal_states.sort(key=lambda s: (s.upper_total, s.yahtzee_eligible))

    upper_total = np.array(
        [s.upper_total for s in terminal_states],
        dtype=np.uint8,
    )
    yahtzee_eligible = np.array(
        [s.yahtzee_eligible for s in terminal_states],
        dtype=bool,
    )
    V = np.zeros(len(terminal_states), dtype=np.float32)

    save_shard(
        TERMINAL_LEVEL,
        FULL_MASK,
        merge=False,
        upper_total=upper_total,
        yahtzee_eligible=yahtzee_eligible,
        V=V,
    )

    print(
        f"Wrote terminal shard for level {TERMINAL_LEVEL}: "
        f"mask={FULL_MASK:013b}, rows={len(terminal_states):,}"
    )


if __name__ == "__main__":
    main()