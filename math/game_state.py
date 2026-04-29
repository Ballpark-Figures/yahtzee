from scoring import *
from dataclasses import dataclass

NUM_CATEGORIES = 13

ONES, TWOS, THREES, FOURS, FIVES, SIXES = range(6)
THREE_KIND = 6
FOUR_KIND = 7
FULL_HOUSE = 8
SMALL_STRAIGHT = 9
LARGE_STRAIGHT = 10
CHANCE = 11
YAHTZEE = 12

UPPER_BONUS_THRESHOLD = 63
UPPER_BONUS = 35
EXTRA_YAHTZEE_BONUS = 100

@dataclass(frozen=True, slots=True)
class GameState:
    filled_mask: int
    upper_total: int
    lower_total: int
    num_yahtzees: int

    def is_filled(self, category: int) -> bool:
        return bool(self.filled_mask & (1 << category))
    
    def fill(self, category: int, dice_state: np.ndarray, is_joker: bool=False) -> "GameState":
        #TODO: finish this class
        # get list of possible successors given a dice_vec and a state
        # handle multiple yahtzees with jokers

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
    
    def get_successors(self, dice_state):
        successors = []
        for category in self.unused_categories():
            successors.append((category, self.fill(category=category, dice_state=dice_state)))
            if self.is_filled(YAHTZEE) and SCORING_FUNCTIONS[YAHTZEE](dice_state) > 0:
                successors.append((category, self.fill(category=category, dice_state=dice_state, is_joker=True)))
        return successors