"""Concrete BackwardFunctional and ForwardFunctional implementations.

Backward (future-from-state):
  - ExpectedScoreAfter   : E[future score]. Validation control: must match V.
  - ScoreDistAfter       : full distribution of future score.
  - BoxDistAfter         : per-category distribution of future points in that box.
  - PTopBonusAfter       : P(upper-section bonus contributes to final score).

Forward (past-to-state):
  - ScoreDistBefore      : joint G(s, x) = P(reach s AND scored x along the way).
  - BoxDistBefore        : joint per-box distribution leading to s.
"""
import numpy as np

from constants import (
    NUM_CATEGORIES, SIXES, YAHTZEE, UPPER_BONUS, UPPER_BONUS_THRESHOLD,
    EXTRA_YAHTZEE_BONUS, YAHTZEE_POINTS,
)
from framework import BackwardFunctional, ForwardFunctional, shift_right_per_row


# Length covering the worst-case Yahtzee score: 215 upper (incl bonus)
# + 235 lower + 12 * 100 extra-yahtzee bonuses = 1650.
TOTAL_SCORE_L = 1650

# Max single-box value: Yahtzee (50). Use 51 as the per-box length.
BOX_SCORE_L = 51


# ========================================================================
# Backward
# ========================================================================

class ExpectedScoreAfter(BackwardFunctional):
    """E[score from now until game end | at s, play optimally]. Equals V."""
    name = "expected_score_after"
    value_shape = ()
    value_dtype = np.float32

    def terminal_value(self, upper_total, yahtzee_eligible):
        return np.float32(0.0)

    def stage_C(self, step_info, future_at_succ, s_idx, d_idx):
        reward = step_info["immediate_reward"][s_idx, d_idx].astype(np.float32)
        return reward + future_at_succ


class ScoreDistAfter(BackwardFunctional):
    """Distribution of total points scored from this state to game end."""
    name = "score_dist_after"
    value_shape = (TOTAL_SCORE_L,)
    value_dtype = np.float32

    def terminal_value(self, upper_total, yahtzee_eligible):
        v = np.zeros(self.value_shape, dtype=np.float32)
        v[0] = 1.0
        return v

    def stage_C(self, step_info, future_at_succ, s_idx, d_idx):
        # Per-row shift of future_at_succ by immediate_reward.
        shifts = step_info["immediate_reward"][s_idx, d_idx].astype(np.int32)
        return shift_right_per_row(future_at_succ, shifts).astype(np.float32)


class BoxDistAfter(BackwardFunctional):
    """For each box c, distribution of points placed in box c going forward.

    Per state s and per box c, gives a (BOX_SCORE_L,) distribution. If c is
    already filled in s, the distribution is degenerate at 0 (already locked).
    """
    name = "box_dist_after"
    value_shape = (NUM_CATEGORIES, BOX_SCORE_L)
    value_dtype = np.float32

    def terminal_value(self, upper_total, yahtzee_eligible):
        v = np.zeros(self.value_shape, dtype=np.float32)
        v[:, 0] = 1.0
        return v

    def stage_C(self, step_info, future_at_succ, s_idx, d_idx):
        chosen_cat = step_info["category"][s_idx, d_idx]
        points = step_info["points"][s_idx, d_idx]   # int16; box value (no bonuses)
        M = future_at_succ.shape[0]

        result = future_at_succ.copy()
        # In the chosen box, the box value is now exactly `points` (delta_points)
        # and no further box-c contributions will happen. Replace the chosen-box
        # row with delta_points.
        rows = np.arange(M)
        result[rows, chosen_cat] = 0.0
        result[rows, chosen_cat, points.astype(np.int32)] = 1.0
        return result


class PTopBonusAfter(BackwardFunctional):
    """P(upper-section bonus contributes to final score, under optimal play).

    Implemented via terminal indicator (1 if upper_total reached 63, else 0).
    No per-step contribution -- just propagation.
    """
    name = "p_top_bonus_after"
    value_shape = ()
    value_dtype = np.float32

    def terminal_value(self, upper_total, yahtzee_eligible):
        return np.float32(1.0 if upper_total >= UPPER_BONUS_THRESHOLD else 0.0)

    def stage_C(self, step_info, future_at_succ, s_idx, d_idx):
        return future_at_succ.copy()


# ========================================================================
# Forward
# ========================================================================

class ScoreDistBefore(ForwardFunctional):
    """Joint distribution G(s, x) = P(reach s AND scored x along the way).

    Sum over x: P(reach s under optimal play). The full distribution at any
    level can be obtained by summing G(s, .) across all s at that level.
    Conditional distribution (score | reach s) is G(s, .) / G(s, .).sum().
    """
    name = "score_dist_before"
    value_shape = (TOTAL_SCORE_L,)
    value_dtype = np.float32

    def initial_value(self):
        v = np.zeros(self.value_shape, dtype=np.float32)
        v[0] = 1.0
        return v

    def stage_C(self, step_info, G_C_sel, s_idx, d_idx):
        shifts = step_info["immediate_reward"][s_idx, d_idx].astype(np.int32)
        return shift_right_per_row(G_C_sel, shifts).astype(np.float32)


class BoxDistBefore(ForwardFunctional):
    """For each box c, joint distribution of (points in box c, reach s).

    Mirrors BoxDistAfter from the other side: per state s and box c, an
    unnormalized distribution over the (possibly already-realized) box value.
    For unfilled boxes the distribution is concentrated at 0 (weighted by
    P(reach s)).
    """
    name = "box_dist_before"
    value_shape = (NUM_CATEGORIES, BOX_SCORE_L)
    value_dtype = np.float32

    def initial_value(self):
        v = np.zeros(self.value_shape, dtype=np.float32)
        v[:, 0] = 1.0
        return v

    def stage_C(self, step_info, G_C_sel, s_idx, d_idx):
        chosen_cat = step_info["category"][s_idx, d_idx]
        points = step_info["points"][s_idx, d_idx]
        M = G_C_sel.shape[0]

        # For each (m), we shift G_C_sel[m, chosen_cat[m], :] right by points[m].
        # All other boxes pass through unchanged.
        result = G_C_sel.copy()
        rows = np.arange(M)
        chosen_slice = G_C_sel[rows, chosen_cat]   # (M, BOX_SCORE_L)
        shifted = shift_right_per_row(chosen_slice, points.astype(np.int32))
        result[rows, chosen_cat] = shifted.astype(np.float32)
        return result