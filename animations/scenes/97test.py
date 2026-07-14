from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice


class Test(YahtzeeScene):
    def setup_scene(self):
        self.scorecard = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        self.board = DiceBoard()
        self.board.place_initial([1, 2, 3, 4, 5])

    @subscene
    def roll_for_sixes(self):
        self.add(self.scorecard)
        self.play(
            FadeIn(self.board.lines),
            *[FadeIn(d) for d in self.board.dice],
        )
        self.wait(0.4)

        # First example: roll up to four 6's (6's start on the right, cross left).
        self.play(*self.board.first_roll([3, 2, 4, 6, 6]))
        self.wait(0.3)
        self.play(*self.board.keep([3, 4]))
        self.wait(0.15)
        self.play(*self.board.roll_rest([5, 6, 1]))
        self.wait(0.3)
        self.play(*self.board.keep([3, 4, 1]))
        self.wait(0.15)
        self.play(*self.board.roll_rest([6, 2]))
        self.wait(0.5)

        dice = self.board.dice

        # ── Upper section ────────────────────────────────────────────────────
        # Each call detects the result from the dice and animates it. Sixes come
        # straight from the roll; the rest are set up with morph_dice.
        self.scorecard.upper(self, dice, 6)
        self.wait(0.3)

        # Order crosses 63 on Fives; Twos has no 2's, so it auto-scores 0 (X).
        top_plan = [
            (3, [3, 3, 3, 2, 5]),   # Threes -> 9   (33)
            (4, [4, 4, 4, 1, 6]),   # Fours  -> 12  (45)
            (5, [5, 5, 5, 5, 2]),   # Fives  -> 20  (65)  ← crosses 63
            (2, [1, 3, 4, 5, 6]),   # Twos   ->  0  (X)
            (1, [1, 1, 1, 4, 6]),   # Ones   ->  3  (68)
        ]
        for face, vals in top_plan:
            morph_dice(self, dice, vals)
            self.wait(0.1)
            self.scorecard.upper(self, dice, face)
            self.wait(0.25)

        # ── Lower section ────────────────────────────────────────────────────
        # Each method decides success vs. a 0 (red-X) from the dice it's given.
        lower_plan = [
            (self.scorecard.chance,          [3, 4, 6, 2, 5]),
            (self.scorecard.three_of_a_kind, [5, 5, 5, 2, 3]),
            (self.scorecard.four_of_a_kind,  [6, 6, 6, 6, 1]),
            (self.scorecard.full_house,      [5, 5, 5, 2, 2]),
            (self.scorecard.small_straight,  [3, 1, 6, 2, 4]),
            (self.scorecard.large_straight,  [2, 5, 1, 4, 3]),
        ]
        for score_fn, vals in lower_plan:
            morph_dice(self, dice, vals)
            self.wait(0.1)
            score_fn(self, dice)
            self.wait(0.25)

        # Yahtzee (50), then two bonus Yahtzees sent to the Yahtzee square.
        yahtzee_box = self.scorecard.value_cells[11]
        for vals in ([4, 4, 4, 4, 4], [6, 6, 6, 6, 6], [2, 2, 2, 2, 2]):
            morph_dice(self, dice, vals)
            self.wait(0.1)
            self.scorecard.yahtzee(self, dice, bonus_square=yahtzee_box)
            self.wait(0.25)

        self.wait(1.0)
