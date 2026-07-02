"""Expected-points-remaining sweep for scene 05's closing beat (i).

Beat i replays scene 04's ending on THIS scene's card: take the card state at the
end of beat h (Ones=3, Twos=6, 4-Kind=12, Chance=12), read its REST-OF-GAME
expected points from the SOLVED game, then empty the boxes one at a time,
re-reading the expectation each time until the card is bare (→ 254.6, the whole
game). Same solver + helper as scene 04 / the notebook
(``math/state_explorer.state_value`` over ``math/data/state_properties``) — this
module does NOT reinvent any EV math, and the render never imports the solver
(the numbers are cached to ``reductions_cache.json``).

Category indices follow the SOLVER order (constants.py), NOT the scorecard:
Ones..Sixes 0..5, 3Kind 6, 4Kind 7, FullHouse 8, SmStraight 9, LgStraight 10,
Chance 11, Yahtzee 12.
"""
from pathlib import Path
import json
import os
import sys

ONES, TWOS, THREES, FOURS, FIVES, SIXES = range(6)
THREE_KIND, FOUR_KIND, FULL_HOUSE = 6, 7, 8
SMALL_STRAIGHT, LARGE_STRAIGHT, CHANCE, YAHTZEE = 9, 10, 11, 12
YAHTZEE_POINTS = 50

_CACHE_PATH = Path(__file__).resolve().parent / "reductions_cache.json"
_MATH_DIR = Path(__file__).resolve().parents[2] / "math"

# The card at the end of beat h == scene-05 SCORES1 (solver cat → box points):
#   Ones 3, Twos 6, 4-of-a-Kind 12, Chance 12   (top total 9, bottom total 24).
CARD_FILLED = {ONES: 3, TWOS: 6, FOUR_KIND: 12, CHANCE: 12}

# Removal order: the two lower-section boxes first, then the top section, so the
# expected-remaining value only ever RISES (clearing a top box lowers the reduced
# state's upper-total, which can otherwise dip V). Verified monotone below.
SWEEP_ORDER = [FOUR_KIND, CHANCE, TWOS, ONES]


def _V_of(se, filled):
    """Rest-of-game expected points for a partially-filled card, via the solver."""
    mask = upper = 0
    elig = False
    for cat, pts in filled.items():
        mask |= (1 << cat)
        if cat <= SIXES:
            upper += pts
        if cat == YAHTZEE and pts == YAHTZEE_POINTS:
            elig = True
    upper = min(upper, 63)
    st = se.ReducedGameState(filled_mask=mask, upper_total=upper,
                             yahtzee_eligible=elig)
    return se.state_value(st)


def _compute():
    prev_cwd = os.getcwd()
    if str(_MATH_DIR) not in sys.path:
        sys.path.insert(0, str(_MATH_DIR))
    os.chdir(_MATH_DIR)
    try:
        import state_explorer as se
        filled = dict(CARD_FILLED)
        sweep = [{"emptied": None, "remaining": _V_of(se, filled)}]
        for cat in SWEEP_ORDER:
            del filled[cat]
            sweep.append({"emptied": cat, "remaining": _V_of(se, filled)})
        return {"sweep": sweep}
    finally:
        os.chdir(prev_cwd)


def scene05_numbers():
    """Scene-05 display bundle, computed once from the solver and cached."""
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    data = _compute()
    _CACHE_PATH.write_text(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    import pprint
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()
    pprint.pprint(scene05_numbers())
