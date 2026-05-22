"""
Validate backward scalar aggregates.

Run from project root:

    python validate_backward_aggregates.py
"""

from __future__ import annotations

import os

import numpy as np

from constants import NUM_CATEGORIES
from state_properties import STATE_PROPERTIES_DIR, load_shard


EXPECTED_SCORE_AFTER_CHECK = "expected_score_after_check"
P_TOP_BONUS_AFTER = "p_top_bonus_after"


def list_masks_for_level(level: int) -> list[int]:
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []

    masks = []
    for filename in os.listdir(level_dir):
        if filename.endswith(".npz"):
            masks.append(int(filename[:-4], 2))

    return sorted(masks)


def main() -> None:
    worst_v_error = 0.0
    worst_bonus_low = 0.0
    worst_bonus_high = 0.0
    checked = 0

    initial_p_bonus = None
    initial_ev_check = None
    initial_v = None

    for level in range(NUM_CATEGORIES + 1):
        for mask in list_masks_for_level(level):
            with load_shard(level, mask) as shard:
                ev_check = shard[EXPECTED_SCORE_AFTER_CHECK].astype(np.float64)
                p_bonus = shard[P_TOP_BONUS_AFTER].astype(np.float64)

                if "V" in shard.files:
                    v = shard["V"].astype(np.float64)
                    v_error = np.max(np.abs(ev_check - v)) if len(v) else 0.0
                    worst_v_error = max(worst_v_error, float(v_error))

                worst_bonus_low = min(worst_bonus_low, float(np.min(p_bonus)) if len(p_bonus) else 0.0)
                worst_bonus_high = max(worst_bonus_high, float(np.max(p_bonus - 1.0)) if len(p_bonus) else 0.0)
                checked += len(ev_check)

                if level == 0 and mask == 0:
                    initial_ev_check = float(ev_check[0])
                    initial_p_bonus = float(p_bonus[0])
                    initial_v = float(shard["V"][0])

    print(f"checked states:                  {checked:,}")
    print(f"initial V:                       {initial_v:.12f}")
    print(f"initial expected after check:    {initial_ev_check:.12f}")
    print(f"initial p top bonus after:       {initial_p_bonus:.12f}")
    print()
    print(f"worst abs V reconstruction err:  {worst_v_error:.12g}")
    print(f"worst p_bonus below 0:           {worst_bonus_low:.12g}")
    print(f"worst p_bonus above 1:           {worst_bonus_high:.12g}")

    if worst_v_error > 1e-3:
        raise SystemExit("V reconstruction error is too large.")

    if worst_bonus_low < -1e-10 or worst_bonus_high > 1e-10:
        raise SystemExit("p_top_bonus_after is outside [0, 1].")

    print("validation passed")


if __name__ == "__main__":
    main()