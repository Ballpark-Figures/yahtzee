"""Reduced GameState for backward-induction / value-iteration use.

Drops state variables that don't affect future decisions or future rewards:
  - lower_total: pure accumulator; folded into the immediate reward when a
    lower-section category is filled.
  - num_yahtzees beyond a single eligibility bit: extra-yahtzee bonuses
    (+100 each) are folded into the immediate reward at the moment they're
    earned (joker fills while yahtzee_eligible is True).

upper_total is capped at UPPER_BONUS_THRESHOLD (63) -- above 63 the +35
bonus is locked in and additional upper points just become immediate reward.
The threshold-crossing bonus is also emitted as part of the immediate reward.

In effect, total expected score from a state = expected sum of immediate
rewards along an optimal play-out from that state. This makes
ReducedGameState the right abstraction for V(s) = E[reward + V(s')] dynamic
programming.
"""
from dataclasses import dataclass

from constants import *
from precomputed import SCORE_ROWS, JOKER_SCORE_ROWS, IS_YAHTZEE_T
from game_state_base import GameStateBase


@dataclass(frozen=True, slots=True)
class ReducedGameState(GameStateBase):
    filled_mask: int
    upper_total: int        # always in [0, UPPER_BONUS_THRESHOLD]
    yahtzee_eligible: bool  # True iff YAHTZEE box was scored as 50

    def __reduce__(self):
        return (
            ReducedGameState,
            (self.filled_mask, self.upper_total, self.yahtzee_eligible),
        )

    def __repr__(self) -> str:
        filled = [CATEGORY_NAMES[c] for c in self.used_categories()]
        return (
            f"ReducedGameState(filled={filled}, "
            f"upper={self.upper_total}, eligible={self.yahtzee_eligible})"
        )

    def fill_by_idx(self, category: int, dice_idx: int, is_joker: bool = False):
        """Return (immediate_reward, new_state).

        The reward bundles everything that *would* have been accumulated into
        state in the full representation:
          - base points scored for the category
          - + UPPER_BONUS if this fill crosses the upper-section threshold
          - + EXTRA_YAHTZEE_BONUS if a joker fill while yahtzee_eligible
        """
        if self.is_filled(category):
            raise ValueError(f"Category {category} is already filled")

        if is_joker:
            if not self.is_filled(YAHTZEE):
                raise ValueError("Can't have a joker without getting a Yahtzee first")
            if not IS_YAHTZEE_T[dice_idx]:
                raise ValueError("Can't use a joker without rolling a Yahtzee")
            points = JOKER_SCORE_ROWS[dice_idx][category]
        else:
            points = SCORE_ROWS[dice_idx][category]

        reward = points
        new_mask = self.filled_mask | (1 << category)

        # Upper section: bookkeep proximity to threshold, emit bonus on crossing.
        if category <= SIXES:
            old_upper = self.upper_total
            new_upper = min(old_upper + points, UPPER_BONUS_THRESHOLD)
            if old_upper < UPPER_BONUS_THRESHOLD and old_upper + points >= UPPER_BONUS_THRESHOLD:
                reward += UPPER_BONUS
        else:
            new_upper = self.upper_total

        # Extra-Yahtzee bonus, when applicable.
        if is_joker and self.yahtzee_eligible:
            reward += EXTRA_YAHTZEE_BONUS

        # Eligibility flips True the moment YAHTZEE is filled with a 50.
        if category == YAHTZEE and points == YAHTZEE_POINTS:
            new_eligible = True
        else:
            new_eligible = self.yahtzee_eligible

        new_state = ReducedGameState(
            filled_mask=new_mask,
            upper_total=new_upper,
            yahtzee_eligible=new_eligible,
        )
        return reward, new_state