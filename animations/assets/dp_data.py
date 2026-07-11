"""Dynamic-programming example numbers for scene 04.

Scene 04 walks through the backward-induction (DP) argument. Every EV it shows is
a REST-OF-GAME expectation ("average points until the end of the game") read from
the SOLVED game — the same value function and query helpers the notebook uses
(``math/state_explorer.py`` over ``math/data/state_properties``). This module does
NOT reinvent the reroll math; it calls the shared helpers and persists the handful
of numbers the scene renders to ``dp_cache.json``.

Two reduced game states drive the scene (upper_total capped at 63, Yahtzee already
used so not eligible — i.e. deep into a realistic game):
  * ``state_1box``  — everything filled EXCEPT Large Straight (the running example).
  * ``state_2box``  — everything filled EXCEPT 4-of-a-Kind AND Large Straight.

Because Large Straight is the only open box in ``state_1box``, its final-roll value
is exactly 40 or 0 (joker included: once Yahtzee is used, a rolled five-of-a-kind
forces a 40 into Large Straight), so a keep's ``p40 = ev / 40`` and ``p0 = 1-p40``.

Category indices follow the SOLVER order (constants.py), NOT the scorecard:
Ones..Sixes = 0..5, 3Kind=6, 4Kind=7, FullHouse=8, SmStraight=9, LgStraight=10,
Chance=11, Yahtzee=12.

Public API:
  * ``values_to_vec(values)``  – [1,2,3,4,6] → (1,1,1,1,0,1) count-vector.
  * ``scene04_numbers()``      – the display bundle, cached to ``dp_cache.json``
                                 (regenerated from the solver when the cache is
                                 absent; render never imports the solver).
"""
from pathlib import Path
import json
import os
import sys

# ── solver category indices (mirrored from math/constants.py) ─────────────────
ONES, TWOS, THREES, FOURS, FIVES, SIXES = range(6)
THREE_KIND, FOUR_KIND, FULL_HOUSE = 6, 7, 8
SMALL_STRAIGHT, LARGE_STRAIGHT, CHANCE, YAHTZEE = 9, 10, 11, 12
YAHTZEE_POINTS = 50

# solver category NAMES, in solver order (must match math/constants.py exactly).
CATEGORY_NAMES = [
    "Ones", "Twos", "Threes", "Fours", "Fives", "Sixes",
    "3Kind", "4Kind", "FullHouse", "SmStraight", "LgStraight", "Chance", "Yahtzee",
]

_CACHE_PATH = Path(__file__).resolve().parent / "dp_cache.json"
_MATH_DIR = Path(__file__).resolve().parents[2] / "math"


# ── pure dice helper (no solver) ──────────────────────────────────────────────
def values_to_vec(values):
    """[1,2,3,4,6] → (1,1,1,1,0,1) count-vector (Ones..Sixes)."""
    v = [0] * 6
    for x in values:
        v[x - 1] += 1
    return tuple(v)


# ── solver-backed cache generation (only runs when the cache is missing) ──────
# The named keeps the scene cycles through, as value-tuples.
_SECOND_REROLL_ROLL = [1, 2, 3, 4, 6]          # beat d/e
_SECOND_REROLL_KEEPS = {"1234": (1, 2, 3, 4), "34": (3, 4),
                        "234": (2, 3, 4), "246": (2, 4, 6)}
_FIRST_REROLL_ROLL = [1, 2, 4, 4, 6]           # beat g
_FIRST_REROLL_KEEPS = {"124": (1, 2, 4), "24": (2, 4), "246": (2, 4, 6)}

# beat f (stage B). First roll is NOT [1,2,4,4,5] (whose EV 6.67 equals beat e's
# ending 1234 keep) — lead with a different EV so the counter changes on the first
# new set. Keeps are varied sizes (3 / 4 / 2 dice).
_OTHER_ROLLS = [[3, 3, 4, 5, 5], [1, 2, 4, 4, 5], [1, 1, 1, 2, 3]]
# beat h (stage A). Beat g already settled on [1,2,4,4,6] keep 24, so DON'T repeat it
# here (that caused the "24 dips down then back up" bounce); start from the next roll.
_TURN_EV_ROLLS = [[1, 2, 3, 4, 6], [2, 3, 4, 5, 5]]

# beat j montage: (roll, stage). Stage B rolls (2nd reroll, 1 left) are shown in the
# upper row; stage A rolls (1st reroll, 2 left) in the lower row. Chosen so the
# rest-of-game EV climbs toward the turn value (21.2) as the montage walks backward.
_MONTAGE = [([1, 2, 4, 4, 6], "B"), ([2, 3, 5, 5, 6], "B"),
            ([1, 1, 4, 5, 6], "A"), ([3, 3, 3, 4, 5], "A")]

# beat k backward sweep: continues the montage's turn on the SAME running-example
# card (beats c-j, i.e. the scene's FILL_LIST) — which already has 4-Kind and Large
# Straight open — then empties the remaining boxes one at a time until the card is
# bare. So it opens at the montage's turn value (V ≈ 21.2) and climbs to 254.6.
# The 11 boxes filled at the start (solver order; the FILL_LIST values minus the two
# open boxes). upper = 63; Yahtzee scratched to 0, so NOT bonus-eligible.
_SWEEP_FILLED = {ONES: 2, TWOS: 6, THREES: 9, FOURS: 12, FIVES: 10, SIXES: 24,
                 THREE_KIND: 22, FULL_HOUSE: 25, SMALL_STRAIGHT: 30,
                 CHANCE: 17, YAHTZEE: 0}
# the remaining boxes, removed one at a time until the card is empty. Order chosen
# so the expected-remaining value climbs MONOTONICALLY (removing a well-scored upper
# box can otherwise dip V, since it lowers the reduced state's upper-total): clear
# the lower-section boxes first, then the top section, so the number only ever rises.
_SWEEP_ORDER = [YAHTZEE, FULL_HOUSE, THREE_KIND, SIXES, TWOS, ONES, THREES,
                FOURS, FIVES, CHANCE, SMALL_STRAIGHT]

# beat b intro: a plausible MID-GAME card with 5 open boxes (a MIX of top + bottom,
# so filling a top box moves the reduced state's upper_total). We fill the 5 open
# boxes one at a time and watch the solver's "avg points remaining" (state V) tick
# DOWN toward 0. Every `remaining` is state_value of the reduced state after that
# fill — SOURCED from the solver, not invented. The per-box `score`s are illustrative
# example fills (like the example dice elsewhere in the scene); only the top-box
# scores actually move V (via the upper total), which the solver then reflects.
# 8 boxes filled at the start (upper = 4+6+12+8 = 30, under 63; Yahtzee still OPEN so
# NOT yet bonus-eligible; 4-of-a-Kind already MISSED = 0). Top boxes use VARIED counts
# (NOT three-of-each). Open: Fives, Sixes, 3-Kind, Large Straight, Yahtzee. Keep in
# sync with the scene's AVG_START (same 8 filled / 5 open, scorecard order).
_AVG_BASE_FILLED = {ONES: 4, TWOS: 6, THREES: 12, FOURS: 8,
                    FOUR_KIND: 0, FULL_HOUSE: 25, SMALL_STRAIGHT: 30, CHANCE: 19}
# (box, score) fill steps in order — a GOOD (not perfect) finish: we MAKE the Large
# Straight (40) and land the top bonus (Fives 10 + Sixes 24 push the top to 64 —
# slightly over 63 → +35), having already missed 4-of-a-Kind and missing the Yahtzee
# (scratched 0) last → terminal (remaining 0). NB the scores are illustrative fills;
# only the top-box (Fives/Sixes) scores move the solver V (via the upper total).
# Order picked so the counter descends monotonically (verified against the solver).
# NB the scores are illustrative fills; only the top-box (Fives/Sixes) scores move
# the solver V (via the upper total) — the bottom-box scores don't. Order picked so
# the counter descends monotonically (verified against the solver).
_AVG_FILL_SEQ = [(THREE_KIND, 15), (LARGE_STRAIGHT, 40),
                 (FIVES, 10), (SIXES, 24), (YAHTZEE, 0)]


def _keep_ev_by_values(df, value_tuple):
    """EV of the keep whose kept dice equal ``value_tuple`` in a keep_alternatives df."""
    for _, r in df.iterrows():
        if tuple(int(x) for x in r["keep"]) == tuple(value_tuple):
            return float(r["EV"])
    raise KeyError(f"keep {value_tuple} not legal for this roll")


def _compute_scene04():
    """Compute the whole display bundle from the solved game via state_explorer.

    The solver data paths are relative to ``math/`` and ``precomputed`` loads
    pickles from ``data/`` at import, so we chdir into ``math/`` for the duration
    (the state_explorer contract) and restore cwd afterwards.
    """
    prev_cwd = os.getcwd()
    if str(_MATH_DIR) not in sys.path:
        sys.path.insert(0, str(_MATH_DIR))
    os.chdir(_MATH_DIR)
    try:
        import state_explorer as se

        def open_state(open_names, upper=63, elig=False):
            filled = [c for c in CATEGORY_NAMES if c not in open_names]
            return se.ReducedGameState(
                filled_mask=se.mask_from_categories(filled),
                upper_total=upper, yahtzee_eligible=elig,
            )

        state_1box = open_state({"LgStraight"})
        state_2box = open_state({"4Kind", "LgStraight"})

        # beat d/e: roll 12346, second reroll (stage B, 1 left), named keeps.
        dfB = se.keep_alternatives(state_1box, _SECOND_REROLL_ROLL, "B")
        second_reroll = {}
        for name, kv in _SECOND_REROLL_KEEPS.items():
            ev = _keep_ev_by_values(dfB, kv)
            p40 = ev / 40.0
            second_reroll[name] = {"p40": p40, "p0": 1.0 - p40, "ev": ev}

        # beat g: roll 12446, first reroll (stage A, 2 left), named keeps (EV only).
        dfA = se.keep_alternatives(state_1box, _FIRST_REROLL_ROLL, "A")
        first_reroll = {name: {"ev": _keep_ev_by_values(dfA, kv)}
                        for name, kv in _FIRST_REROLL_KEEPS.items()}

        # beat f: other rolls, best stage-B keep set forward + its 40/0/avg.
        other_rolls = []
        for values in _OTHER_ROLLS:
            top = se.keep_alternatives(state_1box, values, "B").iloc[0]
            ev = float(top["EV"])
            p40 = ev / 40.0
            other_rolls.append({
                "values": list(values),
                "keep_vec": [int(x) for x in top["keep_vec"]],
                "p40": p40, "p0": 1.0 - p40, "ev": ev,
            })

        # beat h: first rolls, best stage-A keep set forward + avg; then the turn EV.
        turn_ev_rolls = []
        for values in _TURN_EV_ROLLS:
            top = se.keep_alternatives(state_1box, values, "A").iloc[0]
            turn_ev_rolls.append({
                "values": list(values),
                "keep_vec": [int(x) for x in top["keep_vec"]],
                "ev": float(top["EV"]),
            })
        turn_ev = se.state_value(state_1box)

        # beat i: box choice on roll 11134 — fill 4-Kind vs Large Straight. Each
        # "avg after" is 0 (the roll scores 0 in both) + the continuation value of
        # keeping the OTHER box open (rest-of-game).
        ca = se.category_alternatives(state_2box, [1, 1, 1, 3, 4])

        def cat_row(name):
            r = ca[ca["category"] == name].iloc[0]
            now = float(r["score_points"])
            after = float(r["continuation_EV"])
            return {"now": now, "after": after, "total": float(r["total_EV"])}

        box_choice = {"fill_4kind": cat_row("4Kind"),
                      "fill_lgstraight": cat_row("LgStraight")}

        # beat j: montage — per roll, the optimal keep at its stage + rest-of-game EV.
        montage = []
        for values, stage in _MONTAGE:
            ir = se.inspect_roll(state_2box, values)
            row = ir[ir["stage"].str.startswith(stage)].iloc[0]
            montage.append({
                "values": list(values), "stage": stage,
                "keep_vec": [int(x) for x in row["action_raw"]],
                "ev": float(row["EV"]),
            })
        montage_turn_ev = se.state_value(state_2box)

        # beat k: backward sweep — real solver V as the card empties box by box.
        def V_of(filled):
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

        filled = dict(_SWEEP_FILLED)        # 4-Kind + Lg Straight already open
        sweep = [{"emptied": None, "remaining": V_of(filled)}]
        for cat in _SWEEP_ORDER:            # empty the rest until the card is bare
            del filled[cat]
            sweep.append({"emptied": cat, "remaining": V_of(filled)})

        # beat b: avg points remaining as a 5-open MID-GAME card fills box by box.
        # remaining[0] = V of the 5-open state; each step adds one fill → V drops.
        avg_filled = dict(_AVG_BASE_FILLED)
        avg_remaining = [{"filled": None, "score": None, "remaining": V_of(avg_filled)}]
        for cat, pts in _AVG_FILL_SEQ:
            avg_filled[cat] = pts
            avg_remaining.append({"filled": cat, "score": pts,
                                  "remaining": V_of(avg_filled)})

        return {
            "second_reroll": second_reroll,     # keep-name → {p40, p0, ev}
            "first_reroll": first_reroll,       # keep-name → {ev}
            "other_rolls": other_rolls,         # [{values, keep_vec, p40, p0, ev}]
            "turn_ev_rolls": turn_ev_rolls,     # [{values, keep_vec, ev}]
            "turn_ev": turn_ev,                 # state_value(state_1box) ≈ 10.61
            "box_choice": box_choice,           # fill_4kind / fill_lgstraight
            "montage": montage,                 # [{values, stage, keep_vec, ev}]
            "montage_turn_ev": montage_turn_ev, # state_value(state_2box) ≈ 21.22
            "sweep": sweep,                     # [{emptied, remaining}] → empty card
            "avg_remaining": avg_remaining,     # beat b: [{filled, score, remaining}]
        }
    finally:
        os.chdir(prev_cwd)


def scene04_numbers():
    """The scene-04 display bundle, computed once and cached to dp_cache.json."""
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    data = _compute_scene04()
    _CACHE_PATH.write_text(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    import pprint
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()
    pprint.pprint(scene04_numbers())
