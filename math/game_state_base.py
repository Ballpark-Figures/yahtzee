"""Shared base class for GameState and ReducedGameState.

Holds methods that only read self.filled_mask -- they work identically
regardless of which other fields the subclass carries. The empty __slots__
declaration preserves the slots property of the dataclass subclasses
(without it, subclasses would silently gain a __dict__).
"""
from constants import *
from precomputed import IS_YAHTZEE_T, YAHTZEE_FACE_T


class GameStateBase:
    __slots__ = ()

    # Annotation only -- subclasses provide the actual field.
    filled_mask: int

    def is_filled(self, category: int) -> bool:
        return bool(self.filled_mask & (1 << category))

    def is_terminal(self) -> bool:
        return self.filled_mask == (1 << NUM_CATEGORIES) - 1

    def unused_categories(self):
        return [c for c in range(NUM_CATEGORIES) if not self.is_filled(c)]

    def used_categories(self):
        return [c for c in range(NUM_CATEGORIES) if self.is_filled(c)]

    def num_filled(self) -> int:
        return self.filled_mask.bit_count()

    def legal_categories_by_idx(self, dice_idx: int):
        """Return (is_joker, list_of_legal_categories) for the given dice roll."""
        if IS_YAHTZEE_T[dice_idx] and self.is_filled(YAHTZEE):
            face = YAHTZEE_FACE_T[dice_idx]
            # Tier 1: matching upper category, if open -- forced.
            if not self.is_filled(face):
                return (True, [face])
            # Tier 2: any open lower category.
            open_lower = [c for c in range(THREE_KIND, NUM_CATEGORIES) if not self.is_filled(c)]
            if open_lower:
                return (True, open_lower)
            # Tier 3: only open upper categories remain.
            open_upper = [c for c in range(ONES, SIXES + 1) if not self.is_filled(c)]
            return (True, open_upper)
        return (False, self.unused_categories())