from scoring import *
from constants import *
from dice import *
from dataclasses import dataclass

ALL_DICE_STATES, ALL_DICE_FREQS = dice_state_freqs()

def yahtzee_face(dice_vec):
    if dice_vec.max() == 5:
        return int(np.argmax(dice_vec))
    return None

@dataclass(frozen=True)
class GameState:
    filled_mask: int
    upper_total: int
    lower_total: int
    num_yahtzees: int

    def __repr__(self) -> str:
        filled = [CATEGORY_NAMES[c] for c in self.used_categories()]
        return (
            f"GameState(filled={filled}, "
            f"upper={self.upper_total}, lower={self.lower_total}, "
            f"yahtzees={self.num_yahtzees}"
        )

    def is_filled(self, category: int) -> bool:
        return bool(self.filled_mask & (1 << category))
    
    def fill(self, category: int, dice_state: np.ndarray, is_joker: bool=False) -> "GameState":
        if self.is_filled(category):
            raise ValueError(f"Category {category} is already filled")
        
        new_mask = self.filled_mask | (1 << category)
        new_yahtzees = self.num_yahtzees
        if is_joker:
            if not self.is_filled(YAHTZEE):
                raise ValueError("Can't have a joker without getting a Yahtzee first")
            if SCORING_FUNCTIONS[YAHTZEE](dice_state) == 0:
                raise ValueError("Can't use a joker without rolling a Yahtzee")
            new_points = joker_points(dice_state, category)
            if self.num_yahtzees > 0:
                new_yahtzees = self.num_yahtzees + 1
        else:
            new_points = SCORING_FUNCTIONS[category](dice_state)
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
        
    def is_terminal(self) -> bool:
        return self.filled_mask == (1 << NUM_CATEGORIES) - 1
    
    def total_score(self) -> int:
        upper_bonus = UPPER_BONUS if self.upper_total >= UPPER_BONUS_THRESHOLD else 0
        yahtzee_bonus = EXTRA_YAHTZEE_BONUS * max(self.num_yahtzees - 1, 0)
        return self.upper_total + upper_bonus + self.lower_total + yahtzee_bonus

    def unused_categories(self):
        return [
            category
            for category in range(NUM_CATEGORIES)
            if not self.is_filled(category)
        ]
    
    def used_categories(self):
        return [
            category
            for category in range(NUM_CATEGORIES)
            if self.is_filled(category)
        ]
    
    def num_filled(self):
        return self.filled_mask.bit_count()
    
    def legal_categories(self, dice_state):
        # boolean representing whether it's a joker
        if SCORING_FUNCTIONS[YAHTZEE](dice_state) > 0 and self.is_filled(YAHTZEE):
            face = yahtzee_face(dice_state)
            # Tier 1: matching upper category, if open — forced
            if not self.is_filled(face):
                return (True, [face])
            # Tier 2: any open lower category
            open_lower = [c for c in range(THREE_KIND, NUM_CATEGORIES) if not self.is_filled(c)]
            if open_lower:
                return (True, open_lower)
            # Tier 3: only open upper categories remain
            open_upper = [c for c in range(ONES, SIXES + 1) if not self.is_filled(c)]
            return (True, open_upper)
        return (False, self.unused_categories())
    
    def get_successors(self, dice_state):
        successors = []
        is_joker, categories = self.legal_categories(dice_state)
        for category in categories:
            successors.append((category, self.fill(category=category, dice_state=dice_state, is_joker=is_joker)))
        return successors

    def get_all_successors(self):
        return list({
            successor
            for dice_state in ALL_DICE_STATES
            for successor in self.get_successors(dice_state)
        })