"""First-turn outcome list for scene 10 ("Average Points After First Turn").

Each row is a distinct OPTIMAL first-turn outcome (box + score), ranked by the
expected FINAL game total. For every one of the 252 distinct final rolls we ask
the solved policy the best placement and its value via
``state_explorer.category_alternatives(empty, roll).iloc[0]`` — whose
``total_EV`` is ``banked points + V(resulting reduced state)`` (the same recipe
scene 12 used). Rolls are then GROUPED by their (box, score); each group is one
row, its EV is constant across the group, and the sample dice is the
lexicographically-first sorted roll in the group.

This module does NOT reinvent any math — it calls the shared solver helpers and
persists the result to a COMMITTED ``first_turn_cache.json``; the scene reads that
(render never imports the solver). Regenerate with:
    ../../.venv/bin/python assets/first_turn_data.py      # from animations/
Human-readable provenance lives in ``math/scene10_first_turn_numbers.py``.
"""
from pathlib import Path
import json
import os
import sys

_CACHE_PATH = Path(__file__).resolve().parent / "first_turn_cache.json"
_MATH_DIR = Path(__file__).resolve().parents[2] / "math"

# math category index -> scorecard value-cell row (they differ only at 11/12:
# math CHANCE=11/YAHTZEE=12, scorecard 11=Yahtzee/12=Chance).
_MATH_TO_SC = {11: 12, 12: 11}

# Display label per math category (the list's "Box" column).
DISPLAY_NAMES = {
    0: "Ones", 1: "Twos", 2: "Threes", 3: "Fours", 4: "Fives", 5: "Sixes",
    6: "3 of a Kind", 7: "4 of a Kind", 8: "Full House",
    9: "Sm. Straight", 10: "Lg. Straight", 11: "Chance", 12: "Yahtzee",
}


def math_to_sc(cat):
    return _MATH_TO_SC.get(int(cat), int(cat))


def _compute():
    """Group the 252 rolls' optimal outcomes → ranked list of rows. Reads the
    solved V / policy via state_explorer; the state_explorer contract needs cwd =
    math/ (solver data paths are relative), so chdir for the duration."""
    prev_cwd = os.getcwd()
    if str(_MATH_DIR) not in sys.path:
        sys.path.insert(0, str(_MATH_DIR))
    os.chdir(_MATH_DIR)
    try:
        from precomputed import ALL_DICE_STATES, dice_idx_to_values
        from reduced_game_state import ReducedGameState
        from state_explorer import category_alternatives

        empty = ReducedGameState(filled_mask=0, upper_total=0,
                                 yahtzee_eligible=False)

        groups = {}   # (cat, points) -> {"evs": set, "rolls": [sorted tuple]}
        for idx in range(len(ALL_DICE_STATES)):
            vals = tuple(int(v) for v in dice_idx_to_values(idx))
            top = category_alternatives(empty, idx).iloc[0]
            key = (int(top["category_idx"]), int(top["score_points"]))
            g = groups.setdefault(key, {"evs": set(), "rolls": []})
            g["evs"].add(round(float(top["total_EV"]), 6))
            g["rolls"].append(vals)

        rows = []
        for (cat, pts), g in groups.items():
            assert max(g["evs"]) - min(g["evs"]) < 1e-4, (cat, pts, g["evs"])
            ev = sum(g["evs"]) / len(g["evs"])
            rows.append({
                "cat": cat,
                "sc_row": math_to_sc(cat),
                "box": DISPLAY_NAMES[cat],
                "points": pts,
                "dice": list(min(g["rolls"])),   # lexicographically first
                "ev": ev,
            })
        rows.sort(key=lambda r: -r["ev"])
        return {"outcomes": rows}
    finally:
        os.chdir(prev_cwd)


def first_turn_outcomes():
    """The scene-10 ranked outcome list, computed once and cached to
    first_turn_cache.json."""
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    data = _compute()
    _CACHE_PATH.write_text(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()
    data = first_turn_outcomes()
    for i, r in enumerate(data["outcomes"]):
        dice = "".join(str(d) for d in r["dice"])
        print(f"{i:>4}  sc{r['sc_row']:>2}  {r['box']:14s} {r['points']:>3}  "
              f"{dice:6s}  {r['ev']:7.2f}")
