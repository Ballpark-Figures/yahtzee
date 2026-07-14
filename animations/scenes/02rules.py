from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice, slot_x


class Rules(YahtzeeScene):
    # ── construction ──────────────────────────────────────────────────────────
    # ONE continuous scorecard for the whole scene: entries are filled, scratched,
    # emptied and re-filled in place — the card is never swapped out. Dice live in
    # the right-hand bands for the roll mechanic (a–e), then drop to the vertical
    # centre for the combination showcase (f onward).
    TITLE_Y = 1.5          # combination-title height (above the centred dice)
    CENTER_Y = 0.0         # vertical centre the dice sit at for f–l

    def setup_scene(self):
        self.board = DiceBoard()
        self.board.place_initial([1, 2, 3, 4, 5])
        self.card = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        self.title = None

    def _set_title(self, text, *, run_time=0.4):
        """Swap the floating combination title above the centred dice."""
        new = crisp_text(text, font_size=SCORECARD_FONT_SIZE * 1.2,
                         color=BLACK, font=FONT, weight="BOLD")
        new.move_to([slot_x(2), self.TITLE_Y, 0])
        if self.title is None:
            self.title = new
            self.play(FadeIn(self.title, shift=DOWN * 0.2), run_time=run_time)
        else:
            self.play(Transform(self.title, new), run_time=run_time)

    # ── a. bring scorecard in, THEN dice, THEN walk the highlight down ─────────
    @subscene
    def bring_in(self):
        # scorecard first… (shared slide-in entrance, from the side)
        self.card.slide_in(self, run_time=1.0)
        self.wait(0.2)
        # …then the dice (and guide lines)…
        dice = self.board.dice
        self.play(FadeIn(self.board.lines),
                  *[FadeIn(d, shift=UP * 0.8) for d in dice],
                  run_time=1.0)
        self.wait(0.3)
        # …then "every box gets filled exactly once": walk a flash down all 13
        # rows one at a time (pulse, not hold — it's a travelling highlight).
        self.card.highlight_rows(self, range(13), pulse=True, lag_ratio=0.28, run_time=3.2)

    # ── b. the roll mechanic: save 2 → 3 → 4 sixes, score the Sixes box ────────
    # Copied from the 99test "four 6s" example.
    @subscene
    def roll_mechanic(self):
        b = self.board
        self.play(*b.first_roll([3, 2, 4, 6, 6]), run_time=0.7)
        self.wait(2.3)
        self.play(*b.keep([3, 4]), run_time=0.5)                # keep the two 6s
        self.wait(0.5)
        self.play(*b.roll_rest([5, 6, 1]), run_time=0.7)        # → a third 6
        self.wait(3.3)
        self.play(*b.keep([3, 4, 1]), run_time=0.5)             # keep three 6s
        self.wait(0.5)
        self.play(*b.roll_rest([6, 2]), run_time=0.7)           # → four 6s
        self.wait(3.3)
        self.card.upper(self, b.dice, 6)                        # Sixes → 24

    # ── c. a bad roll → scratch a box with a 0 ─────────────────────────────────
    # Demonstrates the forced scratch on 4-of-a-Kind. This (and the Sixes from b)
    # is wiped in d when the systematic walkthrough begins, so 4-of-a-Kind is free
    # to be scored normally in f.
    @subscene
    def zero_box(self):
        morph_dice(self, self.board.dice, [2, 3, 4, 4, 6], run_time=0.6)
        self.wait(0.3)
        self.card.animate_zero_score(self, 7, self.board.dice)   # 4-of-a-Kind → 0

    # ── d. start "what the boxes mean": empty the card, then the upper section ──
    # The mechanics demo (b's Sixes, c's scratched 4-of-a-Kind) is wiped here so
    # the same card is blank again; then four 5s score the Fives box.
    @subscene
    def top_section(self):
        self.card.reset(self, run_time=0.8)             # empty the card again
        self.wait(0.2)
        self.card.highlight_rows(self, range(6), color=YELLOW, run_time=0.9)
        self.wait(3.0)
        dice = self.board.dice
        morph_dice(self, dice, [5, 5, 5, 5, 2], run_time=0.6)
        self.wait(0.2)
        # (no graying of the odd die — top-section scoring has no fade-out)
        self.card.upper(self, dice, 5)                  # Fives → 20

    # ── e. fill the rest of the top section; cross 63 → +35 bonus ──────────────
    @subscene
    def top_bonus(self):
        dice = self.board.dice
        # Fives (20) is already in from d; fill the other five top boxes, with
        # Threes LAST (only TWO 3s → 6) so it's NOT a triple right before the
        # 3-of-a-Kind, and the +35 bonus still crosses on this final box.
        top_plan = [
            (6, [6, 6, 6, 6, 2]),   # Sixes → 24  (44)   four 6s
            (4, [4, 4, 4, 4, 2]),   # Fours → 16  (60)   four 4s
            (2, [1, 3, 4, 5, 6]),   # Twos  →  0  (60)
            (1, [1, 1, 2, 4, 6]),   # Ones  →  2  (62)   two 1s
            (3, [3, 3, 1, 4, 6]),   # Threes→  6  (68)   two 3s ← crosses 63 here
        ]
        for face, vals in top_plan:
            morph_dice(self, dice, vals, run_time=0.2)
            #self.wait(0.1)
            self.card.upper(self, dice, face, run_time=1.2)
            #self.wait(0.25)

    # ── f. enter the centred-dice showcase; 3-of-a-Kind and 4-of-a-Kind ────────
    @subscene
    def kinds(self):
        dice = self.board.dice
        # lines vanish; dice drop STRAIGHT DOWN to the vertical centre (no reorder)
        self.play(FadeOut(self.board.lines),
                  *[d.animate.move_to([d.get_center()[0], self.CENTER_Y, 0])
                    for d in dice],
                  run_time=1.0)
        morph_dice(self, dice, [5, 2, 5, 3, 5], run_time=0.6)   # three 5s (spread)
        self._set_title("3 of a Kind")
        self.wait(0.1)
        self.card.three_of_a_kind(self, dice)           # → 20
        self.wait(0.4)

        self._set_title("4 of a Kind")
        morph_dice(self, dice, [6, 6, 1, 6, 6], run_time=0.6)   # four 6s (spread)
        self.wait(0.1)
        self.card.four_of_a_kind(self, dice)            # → 25

    # ── g. full house: only the colored boxes move (no pips) ───────────────────
    @subscene
    def full_house(self):
        self._set_title("Full House")
        self.wait(1.0)
        dice = self.board.dice
        morph_dice(self, dice, [5, 2, 5, 2, 5], run_time=0.6)   # triple/pair interleaved
        self.wait(1.0)
        self.card.full_house(self, dice)                # → 25

    # ── h. small straight (gray unused), then large straight ───────────────────
    # Colored boxes move (no pips); the dice glide back home as the boxes fly off.
    @subscene
    def straights(self):
        dice = self.board.dice
        self._set_title("Small Straight")
        morph_dice(self, dice, [3, 1, 6, 2, 4], run_time=0.6)
        self.wait(0.1)
        # the unused-die gray is now part of small_straight itself
        self.card.small_straight(self, dice, y=self.CENTER_Y, run_time=2.0)   # → 30
        self.wait(0.2)

        self._set_title("Large Straight")
        morph_dice(self, dice, [2, 5, 1, 4, 3], run_time=0.3)
        self.wait(0.1)
        self.card.large_straight(self, dice, y=self.CENTER_Y, run_time=2.0)   # → 40

    # ── i. Yahtzee ────────────────────────────────────────────────────────────
    @subscene
    def yahtzee(self):
        self._set_title("Yahtzee")
        dice = self.board.dice
        morph_dice(self, dice, [5, 5, 5, 5, 5], run_time=0.6)
        self.wait(0.1)
        self.card.yahtzee(self, dice, y=self.CENTER_Y)  # → 50

    # ── j. Chance ─────────────────────────────────────────────────────────────
    @subscene
    def chance(self):
        self._set_title("Chance")
        dice = self.board.dice
        morph_dice(self, dice, [2, 3, 4, 4, 6], run_time=0.6)
        self.wait(1.5)
        self.card.chance(self, dice)                    # → 19

    # ── k. Joker, no bonus: scratch Yahtzee + empty Fours and Large Straight, ──
    # then a 4s Yahtzee fills the matching upper Fours box, and a 5s Yahtzee fills
    # the Large Straight (Joker rules — full points).
    @subscene
    def joker_fill(self):
        card = self.card
        # scratch Yahtzee to 0 and empty the matching upper Fours + the Large
        # Straight — one declarative transition; counters reverse together (the
        # bar drops back below 63 as Fours empties).
        card.transition(self, {3: None, 10: None, 11: 0})
        self.wait(2.0)

        dice = self.board.dice
        morph_dice(self, dice, [4, 4, 4, 4, 4], run_time=0.6)    # a 4s Yahtzee
        self.wait(1.0)
        self._set_title("Extra Yahtzee")                # carries into l as well
        self.wait(2.0)
        card.joker_fill(self, dice, 3, 20, y=self.CENTER_Y)      # → Fours (re-crosses 63)
        self.wait(2.5)
        morph_dice(self, dice, [5, 5, 5, 5, 5], run_time=0.6)    # a 5s Yahtzee
        self.wait(0.3)
        card.joker_fill(self, dice, 10, 40, y=self.CENTER_Y)     # → Large Straight (40)

    # ── l. real-50 case: turn the 0 into a 50, empty 4-of-a-Kind, then a 6s ─────
    # Yahtzee fills 4-of-a-Kind AND pays the +100 bonus.
    @subscene
    def yahtzee_bonus(self):
        card = self.card
        # turn Yahtzee 0 → 50 AND empty 4-of-a-Kind at the same time
        card.transition(self, {11: 50, 7: None})
        self.wait(0.2)

        dice = self.board.dice
        morph_dice(self, dice, [6, 6, 6, 6, 6], run_time=0.6)    # a 6s Yahtzee
        self.wait(0.2)
        # Yahtzee box now holds a real 50, so this joker_fill knows to do the
        # rainbow jump-spin and pay the +100 bonus on its own.
        card.joker_fill(self, dice, 7, 30, y=self.CENTER_Y)      # → 4-of-a-Kind (30) +100
