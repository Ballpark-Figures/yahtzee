"""Precomputed lookup tables for scoring.

Built once at module load. Replaces per-call invocations of the scoring
functions with O(1) array lookups indexed by (dice_state_idx, category).
"""
import numpy as np
from constants import *
from dice import dice_state_freqs
from scoring import SCORING_FUNCTIONS

# Canonical ordering of the 252 unique dice states (each a 6-vector of counts).
ALL_DICE_STATES, ALL_DICE_FREQS = dice_state_freqs()
NUM_DICE_STATES = len(ALL_DICE_STATES)

# tuple(dice_vec) -> index into ALL_DICE_STATES.
# Used when something hands us a raw vec and we need its row in the tables.
DICE_IDX = {tuple(int(val) for val in state): idx for idx, state in enumerate(ALL_DICE_STATES)}

# Score for the (dice_state, category) pair under non-joker scoring
# Shape: (NUM_DICE_STATES, NUM_CATEGORIES)
SCORE_TABLE = np.array(
    [
        [SCORING_FUNCTIONS[cat](state) for cat in range(NUM_CATEGORIES)]
        for state in ALL_DICE_STATES
    ],
    dtype=np.int16
)

IS_YAHTZEE = np.array(
    [state.max() == 5 for state in ALL_DICE_STATES],
    dtype=bool
)

YAHTZEE_FACE = np.array(
    [int(np.argmax(state)) if state.max() == 5 else -1 for state in ALL_DICE_STATES],
    dtype=np.int8
)

JOKER_SCORE_TABLE = SCORE_TABLE.copy()
JOKER_SCORE_TABLE[:, SMALL_STRAIGHT] = SMALL_STRAIGHT_POINTS
JOKER_SCORE_TABLE[:, LARGE_STRAIGHT] = LARGE_STRAIGHT_POINTS

# Converting numpy to tuples for speed
SCORE_ROWS = tuple(tuple(int(x) for x in row) for row in SCORE_TABLE)
JOKER_SCORE_ROWS = tuple(tuple(int(x) for x in row) for row in JOKER_SCORE_TABLE)
IS_YAHTZEE_T = tuple(bool(x) for x in IS_YAHTZEE)
YAHTZEE_FACE_T = tuple(int(x) for x in YAHTZEE_FACE)

# Convert between raw dice roles, count vectors, and indices

def dice_vec_to_idx(vec) -> int:
    return DICE_IDX[tuple(int(x) for x in vec)]

def dice_idx_to_vec(idx: int) -> np.ndarray:
    return ALL_DICE_STATES[idx]

def dice_values_to_idx(values) -> int:
    vec = np.bincount(np.asarray(values, dtype=int), minlength=7)[1:7]
    return DICE_IDX[tuple(int(x) for x in vec)]

def dice_idx_to_values(idx: int) -> tuple:
    vec = ALL_DICE_STATES[idx]
    return tuple(face for face, count in enumerate(vec, start=1) for _ in range(int(count)))

#HELLO

# Per-(filled_mask, num_yahtzees) transition tables

def _compute_mask_base(filled_mask):
    def is_filled(c):
        return bool(filled_mask & (1 << c))
    yahtzee_filled = is_filled(YAHTZEE)

    unused = [c for c in range(NUM_CATEGORIES) if not is_filled(c)]
    open_upper = [c for c in range(ONES, SIXES + 1) if not is_filled(c)]
    open_lower = [c for c in range(THREE_KIND, NUM_CATEGORIES) if not is_filled(c)]

    base = []
    for dice_idx in range(NUM_DICE_STATES):
        if IS_YAHTZEE_T[dice_idx] and yahtzee_filled:
            face = YAHTZEE_FACE_T[dice_idx]
            if not is_filled(face):
                cats = (face,)
            elif open_lower:
                cats = open_lower
            else:
                cats = open_upper
            is_joker = True
        else:
            cats = unused
            is_joker = False

        for cat in cats:
            if is_joker:
                points = JOKER_SCORE_ROWS[dice_idx][cat]
                ye_kind = 2
            else:
                points = SCORE_ROWS[dice_idx][cat]
                ye_kind = 1 if (cat == YAHTZEE and points == YAHTZEE_POINTS) else 0
            d_upper, d_lower = (points, 0) if cat <= SIXES else (0, points)
            base.append((filled_mask | (1 << cat), d_upper, d_lower, ye_kind))
    return base

def _transitions_for(base, num_yahtzees):
    grouped = {}
    for new_mask, d_upper, d_lower, ye_kind in base:
        if ye_kind == 1:
            new_y = 1
        elif ye_kind == 2 and num_yahtzees > 0:
            new_y = num_yahtzees + 1
        else:
            new_y = num_yahtzees
        bucket = grouped.get(new_mask)
        if bucket is None:
            bucket = set()
            grouped[new_mask] = bucket
        bucket.add((d_upper, d_lower, new_y))
    return tuple((nm, tuple(ts)) for nm, ts in grouped.items())

def _build_transitions():
    table = {}
    for filled_mask in range(1 << NUM_CATEGORIES):
        base = _compute_mask_base(filled_mask)
        if filled_mask & (1 << YAHTZEE):
            max_y = filled_mask.bit_count()
            for y in range(max_y + 1):
                table[(filled_mask, y)] = _transitions_for(base, y)
        else:
            table[(filled_mask, 0)] = _transitions_for(base, 0)
    return table


# Cache the TRANSITIONS table on disk so subsequent runs avoid the ~12s build.
# If you change any scoring / joker / yahtzee-bonus logic above, delete the
# pickle (or just run with TRANSITIONS_REBUILD=1 in the environment).
import os
import pickle

TRANSITIONS_CACHE_PATH = os.path.join("data", "precomputed", "transitions.pkl")


def _load_or_build_transitions():
    force_rebuild = os.environ.get("TRANSITIONS_REBUILD") == "1"
    if not force_rebuild and os.path.exists(TRANSITIONS_CACHE_PATH):
        with open(TRANSITIONS_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    print(f"Building TRANSITIONS table...", flush=True)
    table = _build_transitions()
    os.makedirs(os.path.dirname(TRANSITIONS_CACHE_PATH), exist_ok=True)
    with open(TRANSITIONS_CACHE_PATH, "wb") as f:
        pickle.dump(table, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  cached to {TRANSITIONS_CACHE_PATH}", flush=True)
    return table


TRANSITIONS = _load_or_build_transitions()