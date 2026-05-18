from dataclasses import dataclass
import numpy as np

from constants import *
from precomputed import *

@dataclass(frozen=True, slots=True)
class GameState:
    filled_mask: int
    upper_total: int
    lower_total: int
    num_yahtzees: int

    def __reduce__(self):
        return (GameState, (self.filled_mask, self.upper_total, self.lower_total, self.num_yahtzees))

    def __repr__(self) -> str:
        filled = [CATEGORY_NAMES[c] for c in self.used_categories()]
        return (
            f"GameState(filled={filled}, "
            f"upper={self.upper_total}, lower={self.lower_total}, "
            f"yahtzees={self.num_yahtzees}"
        )

    def is_filled(self, category: int) -> bool:
        return bool(self.filled_mask & (1 << category))
    
    def fill_by_idx(self, category: int, dice_idx: int, is_joker: bool=False) -> "GameState":
        if self.is_filled(category):
            raise ValueError(f"Category {category} is already filled")
        
        new_mask = self.filled_mask | (1 << category)
        new_yahtzees = self.num_yahtzees
        if is_joker:
            if not self.is_filled(YAHTZEE):
                raise ValueError("Can't have a joker without getting a Yahtzee first")
            if not IS_YAHTZEE_T[dice_idx]:
                raise ValueError("Can't use a joker without rolling a Yahtzee")
            new_points = JOKER_SCORE_ROWS[dice_idx][category]
            if self.num_yahtzees > 0:
                new_yahtzees = self.num_yahtzees + 1
        else:
            new_points = SCORE_ROWS[dice_idx][category]
            if category == YAHTZEE and new_points == YAHTZEE_POINTS:
                new_yahtzees = 1


        if category <= SIXES:
            return GameState(
                filled_mask=new_mask,
                upper_total=self.upper_total + new_points,
                lower_total=self.lower_total,
                num_yahtzees=new_yahtzees
            )
        else:
            return GameState(
                filled_mask=new_mask,
                upper_total=self.upper_total,
                lower_total=self.lower_total + new_points,
                num_yahtzees=new_yahtzees
            )
        
    def legal_categories_by_idx(self, dice_idx: int):
        if IS_YAHTZEE_T[dice_idx] and self.is_filled(YAHTZEE):
            face=YAHTZEE_FACE_T[dice_idx]
            # Matching upper category if open
            if not self.is_filled(face):
                return (True, [face])
            # Any open lower category
            open_lower = [c for c in range(THREE_KIND, NUM_CATEGORIES) if not self.is_filled(c)]
            if open_lower:
                return (True, open_lower)
            # Any open upper category
            open_upper = [c for c in range(ONES, SIXES + 1) if not self.is_filled(c)]
            return (True, open_upper)
        return (False, self.unused_categories())
    
    def is_terminal(self) -> bool:
        return self.filled_mask == (1 << NUM_CATEGORIES) - 1

    def total_score(self) -> int:
        upper_bonus = UPPER_BONUS if self.upper_total >= UPPER_BONUS_THRESHOLD else 0
        yahtzee_bonus = EXTRA_YAHTZEE_BONUS * max(self.num_yahtzees - 1, 0)
        return self.upper_total + upper_bonus + self.lower_total + yahtzee_bonus

    def unused_categories(self):
        return [c for c in range(NUM_CATEGORIES) if not self.is_filled(c)]

    def used_categories(self):
        return [c for c in range(NUM_CATEGORIES) if self.is_filled(c)]

    def num_filled(self):
        return self.filled_mask.bit_count()
    
    def get_successors_by_idx(self, dice_idx: int):
        successors = []
        is_joker, categories = self.legal_categories_by_idx(dice_idx)
        for category in categories:
            successors.append((category, self.fill_by_idx(category=category, dice_idx=dice_idx, is_joker=is_joker)))
        return successors
    
    def add_successors_to(self, results):
        upper = self.upper_total
        lower = self.lower_total
        for new_mask, transitions in TRANSITIONS[(self.filled_mask, self.num_yahtzees)]:
            bucket = results.get(new_mask)
            if bucket is None:
                bucket = set()
                results[new_mask] = bucket
            for d_upper, d_lower, new_y in transitions:
                bucket.add(GameState(new_mask, upper + d_upper, lower + d_lower, new_y))