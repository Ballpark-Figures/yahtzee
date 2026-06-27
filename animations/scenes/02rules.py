from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice


class Rules(YahtzeeScene):
    # ── construction ──────────────────────────────────────────────────────────
    def setup_scene(self):
        # One dice board for the whole scene; the cards swap underneath it.
        self.board = DiceBoard()
        self.board.place_initial([1, 2, 3, 4, 5])

        # cardA: empty card for the opening (bring-in, highlight, first scored box)
        self.cardA = get_scorecard(center=LEFT_SC, scores=[None] * 14)

        # cardB: a mostly-filled card for the "fill a box with 0" beat. Only the
        # Yahtzee box (idx 11) is left open, so a bad roll has to be scratched.
        #          1  2  3   4   5   6  3k 4k FH SS LS  Y    Ch  Yb
        self.cardB = get_scorecard(center=LEFT_SC,
            scores=[3, 6, 9, 12, 15, 18, 18, 0, 25, 30, 0, None, 17, 0])

        # cardC: empty card for the full top-to-bottom scoring run-through.
        self.cardC = get_scorecard(center=LEFT_SC, scores=[None] * 14)

        # cardD: late-game card for the multiple-Yahtzee rules. Yahtzee box is
        # already scratched to 0; Threes / Fours / 3-of-a-kind / Chance are open.
        #          1  2  3     4     5   6  3k 4k FH SS  LS  Y  Ch    Yb
        self.cardD = get_scorecard(center=LEFT_SC,
            scores=[3, 6, None, None, 15, 18, None, 0, 25, 30, 40, 0, None, 0])

    def _swap(self, old, new, *, run_time=0.8):
        """Fade one card out and the next one in (they share LEFT_SC)."""
        new.set_opacity(0.0)
        self.add(new)
        self.play(FadeOut(old), new.animate.set_opacity(1.0), run_time=run_time)
        self.remove(old)

    # ── a. bring dice in from the bottom, card in from the left ────────────────
    @subscene
    def bring_in(self):
        self.cardA.shift(LEFT * 0.0)          # built at LEFT_SC already
        dice = self.board.dice
        self.play(
            FadeIn(self.cardA, shift=RIGHT * 2.0),
            FadeIn(self.board.lines),
            *[FadeIn(d, shift=UP * 0.8) for d in dice],
            run_time=1.2,
        )
        self.wait(0.4)
        # "every box gets filled exactly once" — walk a highlight down all 13 rows
        self.cardA.highlight_rows(self, range(13), lag_ratio=0.28, run_time=3.2)
        self.wait(0.3)

    # ── b. the roll mechanic: 3 rolls climbing the bands, then score a box ─────
    @subscene
    def roll_mechanic(self):
        b = self.board
        self.play(*b.first_roll([3, 2, 4, 6, 6]), run_time=1.0)
        self.wait(0.3)
        self.play(*b.keep([3, 4]), run_time=0.6)                # keep the two 6s
        self.wait(0.15)
        self.play(*b.roll_rest([5, 5, 1]), run_time=1.0)
        self.wait(0.3)
        self.play(*b.keep([3, 4, 0]), run_time=0.6)             # keep 6,6,5
        self.wait(0.15)
        self.play(*b.roll_rest([5, 2]), run_time=1.0)
        self.wait(0.5)
        # "fill in one of the empty boxes with what you have" → 3 of a kind (5s)
        self.cardA.three_of_a_kind(self, b.dice)
        self.wait(0.6)

    # ── c. a mostly-filled card + a bad roll → scratch a box with a 0 ──────────
    @subscene
    def zero_box(self):
        self._swap(self.cardA, self.cardB, run_time=0.8)
        self.wait(0.2)
        morph_dice(self, self.board.dice, [2, 3, 4, 4, 6], run_time=0.6)
        self.wait(0.3)
        # nothing for Yahtzee here → it gets a red-X 0
        self.cardB.animate_zero_score(self, 11, self.board.dice)
        self.wait(0.6)

    # ── d. top section: 4 sixes, gray the odd die, pips fly in as 24 ───────────
    @subscene
    def top_section(self):
        self._swap(self.cardB, self.cardC, run_time=0.8)
        self.wait(0.2)
        self.cardC.highlight_rows(self, range(6), color=YELLOW, run_time=0.9)
        self.wait(0.2)

        dice = self.board.dice
        morph_dice(self, dice, [6, 6, 6, 6, 2], run_time=0.6)
        self.wait(0.2)
        odd = dice[4]                                   # the lone 2
        self.play(odd.animate.set_opacity(0.25), run_time=0.4)
        self.cardC.upper(self, dice, 6)                 # → 24 in the Sixes box
        self.wait(0.5)

    # ── e. fill the rest of the top section; cross 63 → +35 bonus ──────────────
    @subscene
    def top_bonus(self):
        dice = self.board.dice
        self.play(dice[4].animate.set_opacity(1.0), run_time=0.3)
        top_plan = [
            (3, [3, 3, 3, 2, 5]),   # Threes → 9   (33)
            (4, [4, 4, 4, 1, 6]),   # Fours  → 12  (45)
            (5, [5, 5, 5, 5, 2]),   # Fives  → 20  (65)  ← crosses 63
            (2, [1, 3, 4, 5, 6]),   # Twos   →  0  (X)
            (1, [1, 1, 1, 4, 6]),   # Ones   →  3  (68)
        ]
        for face, vals in top_plan:
            morph_dice(self, dice, vals, run_time=0.6)
            self.wait(0.1)
            self.cardC.upper(self, dice, face)
            self.wait(0.25)
        self.wait(0.4)

    # ── f. 3-of-a-kind and 4-of-a-kind ────────────────────────────────────────
    @subscene
    def kinds(self):
        dice = self.board.dice
        morph_dice(self, dice, [5, 5, 5, 2, 3], run_time=0.6)
        self.wait(0.1)
        self.cardC.three_of_a_kind(self, dice)          # → 20
        self.wait(0.3)
        morph_dice(self, dice, [6, 6, 6, 6, 1], run_time=0.6)
        self.wait(0.1)
        self.cardC.four_of_a_kind(self, dice)           # → 25
        self.wait(0.5)

    # ── g. full house ─────────────────────────────────────────────────────────
    @subscene
    def full_house(self):
        dice = self.board.dice
        morph_dice(self, dice, [5, 5, 5, 2, 2], run_time=0.6)
        self.wait(0.1)
        self.cardC.full_house(self, dice)               # → 25
        self.wait(0.5)

    # ── h. small straight (gray the unused die), then large straight ──────────
    @subscene
    def straights(self):
        dice = self.board.dice
        morph_dice(self, dice, [3, 1, 6, 2, 4], run_time=0.6)
        self.wait(0.1)
        # the 6 is the unused die in the 1-2-3-4 run → gray it before scoring
        unused = next(d for d in dice if d.value == 6)
        self.play(unused.animate.set_opacity(0.25), run_time=0.4)
        self.cardC.small_straight(self, dice)           # → 30
        self.wait(0.3)
        self.play(unused.animate.set_opacity(1.0), run_time=0.3)

        morph_dice(self, dice, [2, 5, 1, 4, 3], run_time=0.6)
        self.wait(0.1)
        self.cardC.large_straight(self, dice)           # → 40
        self.wait(0.5)

    # ── i. Yahtzee ────────────────────────────────────────────────────────────
    @subscene
    def yahtzee(self):
        dice = self.board.dice
        morph_dice(self, dice, [5, 5, 5, 5, 5], run_time=0.6)
        self.wait(0.1)
        self.cardC.yahtzee(self, dice)                  # → 50
        self.wait(0.5)

    # ── j. Chance ─────────────────────────────────────────────────────────────
    @subscene
    def chance(self):
        dice = self.board.dice
        morph_dice(self, dice, [2, 3, 4, 4, 6], run_time=0.6)
        self.wait(0.1)
        self.cardC.chance(self, dice)                   # → 19
        self.wait(0.6)

    # ── k. multiple-Yahtzee rules: scratched-0 case (Joker scoring) ───────────
    # ROUGH / FLAGGED: which boxes the Joker yahtzee fills is a placeholder
    # (Fours for the top case, 3-of-a-kind for the bottom case). See handoff.
    @subscene
    def joker_fill(self):
        self._swap(self.cardC, self.cardD, run_time=0.8)
        self.wait(0.2)
        dice = self.board.dice
        morph_dice(self, dice, [4, 4, 4, 4, 4], run_time=0.6)
        self.wait(0.2)
        # Yahtzee box already 0 → fill the matching top box (Fours) instead
        self.cardD.upper(self, dice, 4)                 # → 16 in Fours
        self.wait(0.5)
        # if the top box were taken too, you fill an open bottom box
        self.cardD.highlight_rows(self, [6, 12], color=YELLOW, run_time=0.9)
        self.wait(0.2)
        self.cardD.three_of_a_kind(self, dice)          # → 20 in 3-of-a-kind
        self.wait(0.6)

    # ── l. multiple-Yahtzee rules: real-50 case → +100 bonus per extra yahtzee ─
    # ROUGH / FLAGGED: the "replace the 0 with 50" staging is a stand-in.
    @subscene
    def yahtzee_bonus(self):
        # turn the scratched 0 into a real 50 so further yahtzees pay the bonus
        zero = self.cardD.value_texts[11]
        fifty = crisp_text("50", font_size=self.cardD.font_size, color=BLACK, font=FONT)
        fifty.move_to(zero.get_center())
        self.play(Transform(zero, fifty), run_time=0.6)
        self.cardD._yahtzee_is_50 = True
        self.wait(0.3)

        morph_dice(self, self.board.dice, [4, 4, 4, 4, 4], run_time=0.6)
        self.wait(0.2)
        self.cardD.animate_yahtzee_bonus(self)          # +100
        self.wait(0.8)
