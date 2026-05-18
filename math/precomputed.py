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