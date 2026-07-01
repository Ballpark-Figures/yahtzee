"""Dynamic-programming example numbers for scene 04.

Scene 04 walks through the backward-induction (DP) argument on the LAST turn of
a solo game, where the whole turn is spent going all-out for ONE open box. Every
EV / probability it shows is therefore an *exact* single-box expectation over the
reroll structure — no whole-game value function is needed, so (like
``score_data.py``) this module does NOT import the solver. It re-implements the
handful of primitives it needs (count-vector scoring + the reroll multinomial)
directly, matching ``math/dice.py`` and ``math/scoring.py`` exactly:

  * dice are 6-vectors of counts (index 0 = Ones … index 5 = Sixes);
  * a reroll of ``n`` dice enumerates 6^n equally-likely rolls, and every
    distribution is expressed over the constant denominator 6^5 = 7776.

Category indices follow the SOLVER order (constants.py), NOT the scorecard:
Ones..Sixes = 0..5, 3Kind=6, 4Kind=7, FullHouse=8, SmStraight=9, LgStraight=10,
Chance=11, Yahtzee=12.

Public API (all values are exact rationals evaluated in float):
  * ``ev_keep(dice, keep, cat, rerolls)``    – EV of keeping ``keep`` with 1 or 2
                                               rerolls remaining, going for ``cat``.
  * ``score_dist_keep(dice, keep, cat)``     – {points: prob} after the LAST reroll.
  * ``best_keep(dice, cat, rerolls)``        – (keep_vec, EV) maximising ``ev_keep``.
  * ``turn_value(cat)``                      – whole last-turn EV, all-out for ``cat``.
  * ``scene04_numbers()``                    – the specific bundle the scene renders,
                                               cached to ``dp_cache.json`` (the
                                               ``turn_value`` sweep is the only slow
                                               part, so it is what gets persisted).

Everything cheap is ``lru_cache``d in-process; only the per-category whole-turn
values are persisted to disk.
"""
from pathlib import Path
from itertools import product
from functools import lru_cache
import json
import numpy as np

# ── constants (mirrored from math/constants.py) ───────────────────────────────
SIDES = 6
N_DICE = 5
DENOM = SIDES ** N_DICE            # 7776 — every distribution's denominator

FULL_HOUSE_POINTS = 25
SMALL_STRAIGHT_POINTS = 30
LARGE_STRAIGHT_POINTS = 40
YAHTZEE_POINTS = 50

# solver category indices
ONES, TWOS, THREES, FOURS, FIVES, SIXES = range(6)
THREE_KIND, FOUR_KIND, FULL_HOUSE = 6, 7, 8
SMALL_STRAIGHT, LARGE_STRAIGHT, CHANCE, YAHTZEE = 9, 10, 11, 12

_CACHE_PATH = Path(__file__).resolve().parent / "dp_cache.json"


# ── dice helpers ──────────────────────────────────────────────────────────────
def values_to_vec(values):
    """[1,2,3,4,6] → (1,1,1,1,0,1) count-vector (Ones..Sixes)."""
    v = [0] * SIDES
    for x in values:
        v[x - 1] += 1
    return tuple(v)


def _vsum(vec):
    return sum((i + 1) * c for i, c in enumerate(vec))


def score(vec, cat):
    """Points for count-vector ``vec`` scored in solver category ``cat``
    (matches math/scoring.py exactly)."""
    if cat < 6:
        return (cat + 1) * vec[cat]
    if cat == THREE_KIND:
        return _vsum(vec) if max(vec) >= 3 else 0
    if cat == FOUR_KIND:
        return _vsum(vec) if max(vec) >= 4 else 0
    if cat == FULL_HOUSE:
        return FULL_HOUSE_POINTS if ((3 in vec and 2 in vec) or (5 in vec)) else 0
    if cat == SMALL_STRAIGHT:
        ok = vec[0] * vec[1] * vec[2] * vec[3] or vec[1] * vec[2] * vec[3] * vec[4] \
            or vec[2] * vec[3] * vec[4] * vec[5]
        return SMALL_STRAIGHT_POINTS if ok else 0
    if cat == LARGE_STRAIGHT:
        ok = vec[0] * vec[1] * vec[2] * vec[3] * vec[4] \
            or vec[1] * vec[2] * vec[3] * vec[4] * vec[5]
        return LARGE_STRAIGHT_POINTS if ok else 0
    if cat == CHANCE:
        return _vsum(vec)
    if cat == YAHTZEE:
        return YAHTZEE_POINTS if max(vec) >= 5 else 0
    raise ValueError(f"bad category {cat}")


@lru_cache(maxsize=None)
def _reroll_dist(keep):
    """Distribution over final count-vectors after rerolling all non-kept dice,
    as a tuple of (final_vec, weight) with weights summing to DENOM (6^5)."""
    ksum = sum(keep)
    n_reroll = N_DICE - ksum
    if n_reroll == 0:
        return ((keep, DENOM),)
    acc = {}
    scale = SIDES ** ksum          # so the total weight is 6^5, not 6^n_reroll
    for roll in product(range(SIDES), repeat=n_reroll):
        v = list(keep)
        for face in roll:
            v[face] += 1
        v = tuple(v)
        acc[v] = acc.get(v, 0) + scale
    return tuple(acc.items())


@lru_cache(maxsize=None)
def _sub_vecs(dice):
    """All keep-subsets of ``dice`` (each face 0..count), as count-vectors."""
    return tuple(product(*[range(c + 1) for c in dice]))


# ── single-box expectations (the whole scene lives here) ───────────────────────
def score_dist_keep(dice, keep, cat):
    """{points: probability} for the FINAL dice after keeping ``keep`` (one reroll
    left) and scoring ``cat``. ``dice`` is unused for the math but kept in the
    signature so callers read naturally."""
    acc = {}
    for v, w in _reroll_dist(tuple(keep)):
        pts = score(v, cat)
        acc[pts] = acc.get(pts, 0) + w
    return {p: w / DENOM for p, w in acc.items()}


@lru_cache(maxsize=None)
def _ev_one_reroll(keep, cat):
    return sum(w * score(v, cat) for v, w in _reroll_dist(keep)) / DENOM


@lru_cache(maxsize=None)
def _value_pre_last_reroll(dice, cat):
    """Best EV obtainable from post-first-reroll dice ``dice`` with ONE reroll
    still to come (choose the keep that maximises the last-reroll EV)."""
    return max(_ev_one_reroll(k, cat) for k in _sub_vecs(dice))


@lru_cache(maxsize=None)
def _ev_two_reroll(keep, cat):
    """EV of keeping ``keep`` with TWO rerolls remaining: reroll now, then play
    the last reroll optimally from whatever we land on."""
    return sum(w * _value_pre_last_reroll(v, cat)
               for v, w in _reroll_dist(keep)) / DENOM


@lru_cache(maxsize=None)
def _value_post_first_roll(dice, cat):
    """Best EV from a fresh roll ``dice`` with two rerolls remaining."""
    return max(_ev_two_reroll(k, cat) for k in _sub_vecs(dice))


def ev_keep(dice, keep, cat, rerolls):
    """EV of keeping ``keep`` from ``dice``, going all-out for ``cat``, with
    ``rerolls`` (1 or 2) rerolls remaining."""
    keep = tuple(keep)
    if rerolls == 1:
        return _ev_one_reroll(keep, cat)
    if rerolls == 2:
        return _ev_two_reroll(keep, cat)
    raise ValueError("rerolls must be 1 or 2")


def best_keep(dice, cat, rerolls):
    """(keep_vec, EV) maximising ``ev_keep`` over all keep-subsets of ``dice``."""
    dice = tuple(dice)
    best, best_ev = None, -1.0
    for k in _sub_vecs(dice):
        ev = ev_keep(dice, k, cat, rerolls)
        if ev > best_ev:
            best, best_ev = k, ev
    return best, best_ev


@lru_cache(maxsize=None)
def _all_initial_states():
    """The 252 distinct opening rolls with their weights (sum = DENOM)."""
    acc = {}
    for roll in product(range(SIDES), repeat=N_DICE):
        v = [0] * SIDES
        for face in roll:
            v[face] += 1
        v = tuple(v)
        acc[v] = acc.get(v, 0) + 1
    return tuple(acc.items())


def turn_value(cat):
    """Expected points from spending a whole last turn (3 rolls, 2 rerolls) all
    going for a single open box ``cat``, under optimal keep decisions."""
    return sum(w * _value_post_first_roll(v, cat)
               for v, w in _all_initial_states()) / DENOM


# ── the concrete bundle the scene renders (persisted) ─────────────────────────
def _compute_scene04():
    ls = LARGE_STRAIGHT
    # beat 2/3: last reroll (1 left), dice 12346, several keeps for Lg Straight.
    d_ls = values_to_vec([1, 2, 3, 4, 6])
    keeps_ls = {
        "1234": values_to_vec([1, 2, 3, 4]),
        "34":   values_to_vec([3, 4]),
        "234":  values_to_vec([2, 3, 4]),
        "246":  values_to_vec([2, 4, 6]),
    }
    second_reroll = {}
    for name, k in keeps_ls.items():
        dist = score_dist_keep(d_ls, k, ls)
        second_reroll[name] = {
            "p40": dist.get(40, 0.0),
            "p0": dist.get(0, 0.0),
            "ev": ev_keep(d_ls, k, ls, 1),
        }

    # beat 4: first reroll (2 left), dice 12446, keeps for Lg Straight (EV only).
    d_ls2 = values_to_vec([1, 2, 4, 4, 6])
    keeps_ls2 = {
        "124": values_to_vec([1, 2, 4]),
        "24":  values_to_vec([2, 4]),
        "246": values_to_vec([2, 4, 6]),
    }
    first_reroll = {name: {"ev": ev_keep(d_ls2, k, ls, 2)}
                    for name, k in keeps_ls2.items()}

    # beat 6: box choice for 11134 between 3-of-a-kind and 4-of-a-kind (last two
    # turns). "Avg points after" = points now + whole last-turn EV of the box we
    # keep open.
    d_box = values_to_vec([1, 1, 1, 3, 4])
    tv_3k = turn_value(THREE_KIND)
    tv_4k = turn_value(FOUR_KIND)
    box_choice = {
        # fill 3-kind now (score it), keep 4-kind for the last turn
        "fill_3kind": {"now": score(d_box, THREE_KIND), "after": tv_4k,
                       "total": score(d_box, THREE_KIND) + tv_4k},
        # zero 4-kind now (11134 makes no 4-kind → 0), keep 3-kind for last turn
        "fill_4kind": {"now": score(d_box, FOUR_KIND), "after": tv_3k,
                       "total": score(d_box, FOUR_KIND) + tv_3k},
    }

    return {
        "second_reroll": second_reroll,   # keep-name → {p40, p0, ev}
        "first_reroll": first_reroll,     # keep-name → {ev}
        "box_choice": box_choice,
        "turn_values": {                  # handy reference for other beats
            "large_straight": turn_value(LARGE_STRAIGHT),
            "three_kind": tv_3k,
            "four_kind": tv_4k,
        },
    }


def scene04_numbers():
    """The scene-04 display bundle, computed once and cached to dp_cache.json."""
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    data = _compute_scene04()
    _CACHE_PATH.write_text(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    import pprint
    pprint.pprint(_compute_scene04())
