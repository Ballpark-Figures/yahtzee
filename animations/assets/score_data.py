"""Score-distribution data for scene 07 (and later 13).

Reads the precomputed optimal-play distributions under ``math/data`` and exposes
them as plain dicts/lists (picklable, cheap to build lazily inside a subscene):

  * ``score_distribution()``      – {score: prob}, the full histogram.
  * ``overlay_by_yahtzee(n)``     – {score: prob} for games with exactly ``n``
                                    EXTRA (100-pt) yahtzee bonuses.
  * ``overlay_by_reduced(k)`` /
    ``overlay_reduced_below(k)``  – {score: prob} sliced by reduced-bonus points.
  * ``bonus_table_rows()``        – per-bonus (label, max, EV, success%) rows.

All probabilities are normalised by the SAME global total, so any overlay's bar
is a strict subset of (never taller than) the corresponding base bar.

The packing constants + reduced-point weights mirror ``math/aggregate_properties``
(stable; copied here so the animations tree doesn't import the solver).
"""
from pathlib import Path
import numpy as np

_REPO = Path(__file__).resolve().parent.parent.parent          # .../yahtzee
_DATA = _REPO / "math" / "data"
_FINAL = _DATA / "final_outcome_dists" / "level_00" / "0000000000000.npz"
_STATE = _DATA / "state_properties" / "level_00" / "0000000000000.npz"

# ── packed-key layout (see math/aggregate_properties.py) ──────────────────────
SCORE_BITS = 11
YAHTZEE_UNIT_BITS = 4
YAHTZEE_UNIT_SHIFT = SCORE_BITS
FLAGS_SHIFT = SCORE_BITS + YAHTZEE_UNIT_BITS
SCORE_MASK = (1 << SCORE_BITS) - 1
YAHTZEE_UNIT_MASK = (1 << YAHTZEE_UNIT_BITS) - 1

FLAG_LARGE_STRAIGHT = 1 << 0
FLAG_SMALL_STRAIGHT = 1 << 1
FLAG_FULL_HOUSE = 1 << 2
FLAG_FOUR_KIND = 1 << 3
FLAG_THREE_KIND = 1 << 4
FLAG_TOP_BONUS = 1 << 5

# reduced-bonus point weights (max regular total, no extra yahtzee, = 10)
RP_EXTRA_YAHTZEE = 4
RP_YAHTZEE = 2
RP_LARGE_STRAIGHT = 2
RP_TOP_BONUS = 2
RP_SMALL_STRAIGHT = 1
RP_FULL_HOUSE = 1
RP_THREE_KIND = 1
RP_FOUR_KIND = 1

# solver box indices (NB: 11 = chance, 12 = yahtzee — reversed vs the scorecard)
BOX_THREE_KIND = 6
BOX_FOUR_KIND = 7
BOX_FULL_HOUSE = 8
BOX_SMALL_STRAIGHT = 9
BOX_LARGE_STRAIGHT = 10
BOX_YAHTZEE = 12

_cache = {}


def _load():
    """(score, yahtzee_units, flags, prob) int/float arrays over the 57,033
    distinct final outcomes; prob normalised to sum 1."""
    if "final" not in _cache:
        with np.load(_FINAL) as z:
            keys = z["keys"].astype(np.uint32)
            prob = z["probs"].astype(np.float64)
        score = (keys & SCORE_MASK).astype(np.int64)
        yu = ((keys >> YAHTZEE_UNIT_SHIFT) & YAHTZEE_UNIT_MASK).astype(np.int64)
        flags = (keys >> FLAGS_SHIFT).astype(np.int64)
        prob = prob / prob.sum()
        _cache["final"] = (score, yu, flags, prob)
    return _cache["final"]


def _reduced_points(yu, flags):
    rp = np.zeros_like(yu)
    rp += RP_EXTRA_YAHTZEE * np.maximum(yu - 1, 0)
    rp += RP_YAHTZEE * (yu >= 1)
    rp += RP_LARGE_STRAIGHT * ((flags & FLAG_LARGE_STRAIGHT) != 0)
    rp += RP_TOP_BONUS * ((flags & FLAG_TOP_BONUS) != 0)
    rp += RP_SMALL_STRAIGHT * ((flags & FLAG_SMALL_STRAIGHT) != 0)
    rp += RP_FULL_HOUSE * ((flags & FLAG_FULL_HOUSE) != 0)
    rp += RP_THREE_KIND * ((flags & FLAG_THREE_KIND) != 0)
    rp += RP_FOUR_KIND * ((flags & FLAG_FOUR_KIND) != 0)
    return rp


def _dist(mask=None):
    """{score: prob} summed over the subset selected by boolean ``mask`` (or all
    outcomes when None). Always normalised by the GLOBAL total."""
    score, yu, flags, prob = _load()
    if mask is None:
        s, p = score, prob
    else:
        s, p = score[mask], prob[mask]
    out = {}
    for sc, pr in zip(s.tolist(), p.tolist()):
        out[sc] = out.get(sc, 0.0) + pr
    return out


def score_distribution():
    """Full final-score distribution, {score: prob}."""
    return _dist()


def overlay_by_yahtzee(n_extra):
    """Games with exactly ``n_extra`` EXTRA (100-pt) yahtzee bonuses.
    One extra bonus ⇒ yahtzee_units == 2 (the 50 plus one +100)."""
    _, yu, _, _ = _load()
    return _dist(yu == n_extra + 1)


def overlay_by_reduced(k):
    """Games whose reduced-bonus points == ``k`` (max regular total = 10)."""
    _, yu, flags, _ = _load()
    rp = _reduced_points(yu, flags)
    return _dist(rp == k)


def overlay_reduced_below(k):
    """Games whose reduced-bonus points < ``k`` (the 'mixed' low tail)."""
    _, yu, flags, _ = _load()
    rp = _reduced_points(yu, flags)
    return _dist(rp < k)


def overlay_yahtzee_bumps():
    """All games with at least one EXTRA yahtzee bonus (yu >= 2) — the right
    bumps revisited in the highlight beats."""
    _, yu, _, _ = _load()
    return _dist(yu >= 2)


def _flag_prob(flag):
    _, _, flags, prob = _load()
    return float(prob[(flags & flag) != 0].sum())


def _box_ev(box_index):
    with np.load(_STATE) as z:
        a = z[f"box_score_dist_after_{box_index:02d}"].astype(np.float64).ravel()
    a = a / a.sum()
    return float((np.arange(len(a)) * a).sum())


def bonus_table_rows():
    """Per-bonus rows for the bar-graph table: top bonus, then the bottom
    section minus chance. Each: (label, max_value, expected_value, pct, fade)."""
    _, yu, _, prob = _load()
    p_yahtzee = float(prob[yu >= 1].sum())          # any yahtzee scored (the 50)
    p_top = _flag_prob(FLAG_TOP_BONUS)
    return [
        {"label": "Top Bonus",      "max_value": 35, "expected_value": 35 * p_top,            "pct": 100 * p_top,                              "fade": False},
        {"label": "3 of a Kind",    "max_value": 30, "expected_value": _box_ev(BOX_THREE_KIND),    "pct": 100 * _flag_prob(FLAG_THREE_KIND),    "fade": True},
        {"label": "4 of a Kind",    "max_value": 30, "expected_value": _box_ev(BOX_FOUR_KIND),     "pct": 100 * _flag_prob(FLAG_FOUR_KIND),     "fade": True},
        {"label": "Full House",     "max_value": 25, "expected_value": _box_ev(BOX_FULL_HOUSE),    "pct": 100 * _flag_prob(FLAG_FULL_HOUSE),    "fade": False},
        {"label": "Small Straight", "max_value": 30, "expected_value": _box_ev(BOX_SMALL_STRAIGHT),"pct": 100 * _flag_prob(FLAG_SMALL_STRAIGHT),"fade": False},
        {"label": "Large Straight", "max_value": 40, "expected_value": _box_ev(BOX_LARGE_STRAIGHT),"pct": 100 * _flag_prob(FLAG_LARGE_STRAIGHT),"fade": False},
        {"label": "Yahtzee",        "max_value": 50, "expected_value": _box_ev(BOX_YAHTZEE),       "pct": 100 * p_yahtzee,                      "fade": False},
    ]
