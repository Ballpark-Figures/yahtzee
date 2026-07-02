"""Line-graph numbers for scene 08 (round # vs average box points, if unfilled).

Scene 08 shows, for each box, the average points that box is still worth given it
hasn't been filled by round R — read from the SOLVED game via the same helper the
notebook plots (``math/state_explorer.future_box_ev_with_yahtzee_bonus_pivot``).
This module does NOT reinvent any math; it calls the shared helper and persists the
handful of series the scene renders to ``line_cache.json`` (render never imports
the solver — it reads the cache).

The plotted lines are exactly the notebook's ``cols`` set:
    3Kind, 4Kind, FullHouse, LgStraight, SmStraight, Yahtzee
where the Yahtzee line is ``YahtzeePlus = Yahtzee + YahtzeeBonus`` (the +100-point
extra-Yahtzee bonuses are folded in, per the scene-08 voiceover). Rounds are 1..13.
"""
from pathlib import Path
import json
import os
import sys

_CACHE_PATH = Path(__file__).resolve().parent / "line_cache.json"
_MATH_DIR = Path(__file__).resolve().parents[2] / "math"

# (solver column name, display label). Order = draw / legend order. The Yahtzee
# entry pulls from the combined YahtzeePlus column built below.
LINES = [
    ("SmStraight", "Small Straight"),
    ("LgStraight", "Large Straight"),
    ("Yahtzee",    "Yahtzee"),          # -> YahtzeePlus (box + 100-pt bonuses)
    ("3Kind",      "3 of a Kind"),
    ("4Kind",      "4 of a Kind"),
    ("FullHouse",  "Full House"),
]


def _compute():
    """Compute the per-round EV series from the solved game via state_explorer.

    Solver data paths are relative to ``math/`` and ``precomputed`` loads pickles
    from ``data/`` at import, so chdir into ``math/`` for the duration (the
    state_explorer contract) and restore cwd afterwards.
    """
    prev_cwd = os.getcwd()
    if str(_MATH_DIR) not in sys.path:
        sys.path.insert(0, str(_MATH_DIR))
    os.chdir(_MATH_DIR)
    try:
        import state_explorer as se

        pivot = se.future_box_ev_with_yahtzee_bonus_pivot()
        pivot["YahtzeePlus"] = pivot["Yahtzee"] + pivot["YahtzeeBonus"]

        rounds = [int(r) for r in pivot.index]
        lines = []
        for col, label in LINES:
            src = "YahtzeePlus" if col == "Yahtzee" else col
            values = [float(pivot.loc[r, src]) for r in pivot.index]
            lines.append({"key": col, "label": label, "values": values})

        return {"rounds": rounds, "lines": lines}
    finally:
        os.chdir(prev_cwd)


def scene08_lines():
    """The scene-08 line series, computed once and cached to line_cache.json."""
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    data = _compute()
    _CACHE_PATH.write_text(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    import pprint
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()
    pprint.pprint(scene08_lines())
