"""Precomputed lookup tables for scoring.

Built once at module load. Replaces per-call invocations of the scoring
functions with O(1) array lookups indexed by (dice_state_idx, category).
"""
import os
import pickle
import numpy as np
from constants import *
from dice import dice_state_freqs, get_all_sub_vecs, get_reroll_results
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

# Keep tables and reroll-outcome distribution
# -------------------------------------------
# A "keep" is the 6-vector of dice you choose to retain before rerolling the
# rest. Any nonneg 6-tuple summing to 0..5 is a valid keep (462 in total).
#
# Indexing mirrors DICE_IDX in style:
#   ALL_KEEPS                : canonical ordering of the 462 keep vectors
#   KEEP_IDX[vec]            : vec -> idx into ALL_KEEPS
#   KEEPS_FOR_DICE[dice_idx] : tuple of keep_idxs valid from that dice state
#   REROLL_OUTCOMES[(dice_idx, keep_idx)]
#       = (final_idxs, numerators), where numerators are integers summing
#         to 6**5 = 7776. The probability of reaching final_idxs[k] from
#         dice_idx by holding keep_idx and rerolling the rest is
#         numerators[k] / 7776.

def _build_reroll_tables():
    keep_set = set()
    for dice_state in ALL_DICE_STATES:
        for sub_vec in get_all_sub_vecs(dice_state):
            keep_set.add(tuple(int(x) for x in sub_vec))
    all_keeps = tuple(sorted(keep_set))
    keep_idx = {v: i for i, v in enumerate(all_keeps)}

    keeps_for_dice = tuple(
        tuple(
            keep_idx[tuple(int(x) for x in sub_vec)]
            for sub_vec in get_all_sub_vecs(ALL_DICE_STATES[dice_idx])
        )
        for dice_idx in range(NUM_DICE_STATES)
    )

    reroll_outcomes = {}
    for dice_index in range(NUM_DICE_STATES):
        for sub_vec in get_all_sub_vecs(ALL_DICE_STATES[dice_index]):
            sub_tup = tuple(int(x) for x in sub_vec)
            ki = keep_idx[sub_tup]
            final_vecs, freqs = get_reroll_results(sub_tup)
            final_idxs = tuple(DICE_IDX[tuple(int(x) for x in final_vec)] for final_vec in final_vecs)
            numerators = tuple(int(freq) for freq in freqs)
            reroll_outcomes[(dice_index, ki)] = (final_idxs, numerators)

    return all_keeps, keep_idx, keeps_for_dice, reroll_outcomes

REROLL_TABLES_CACHE_PATH = os.path.join("data", "precomputed", "reroll_tables.pkl")

def _load_or_build_reroll_tables():
    force_rebuild = os.environ.get("REROLL_TABLES_REBUILD") == "1"
    if not force_rebuild and os.path.exists(REROLL_TABLES_CACHE_PATH):
        with open(REROLL_TABLES_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    print("Building reroll tables...", flush=True)
    bundle = _build_reroll_tables()
    os.makedirs(os.path.dirname(REROLL_TABLES_CACHE_PATH), exist_ok=True)
    with open(REROLL_TABLES_CACHE_PATH, "wb") as f:
        pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  cached to {REROLL_TABLES_CACHE_PATH}", flush=True)
    return bundle

ALL_KEEPS, KEEP_IDX, KEEPS_FOR_DICE, REROLL_OUTCOMES = _load_or_build_reroll_tables()
NUM_KEEPS = len(ALL_KEEPS)

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