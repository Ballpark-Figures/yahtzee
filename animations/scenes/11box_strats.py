from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice, slot_point

# ── Scorecard ROW indices (card order — differs from math order: yahtzee sits
#    ABOVE chance on the card, so yahtzee=11, chance=12) ────────────────────────
R_ONES, R_TWOS, R_THREES, R_FOURS, R_FIVES, R_SIXES = range(6)
R_3KIND, R_4KIND, R_FH, R_SMALL, R_LARGE, R_YAHT, R_CHANCE = 6, 7, 8, 9, 10, 11, 12

# ── Illustrative pre-filled card states (rows 0..12; None = open box) ──────────
# ALL VALUES ARE ILLUSTRATIVE game-states I chose (internally consistent, not
# sourced numbers) — flagged for review. Top-section targets that name "57" sum
# to 57; "63" states hit the bonus.
#                 1s  2s  3s  4s  5s  6s  3k  4k  fh  ss  ls  yz  ch
CARD_B  = [ 3, None,  9, 12, 15, 18, 17, None, 25, 30, None,  0, None]  # 57 top; open twos/4k/lg/chance
CARD_C  = [ 3,  6,  9, 12, 15, 18, 20, 24, 25, None, 40, None, 22]      # 63 top; open sm-straight/yahtzee
CARD_EA = [ 3,  6,  9, 12, 15, 18, 20, 24, 25, None, None, 50, 22]      # open sm + lg straight
CARD_EB = [ 3,  6,  9, 12, 15, 18, 20, 24, 25, 30, None, 50, None]      # sm filled, open lg + chance
CARD_F  = [None]*6 + [20, 24, None, 30, 40, 50, 22]                     # whole top open + full house
CARD_G3 = [ 5,  6,  9, 12, 15, 18, None, None, 25, 30, 40, 50, 22]      # open 3k + 4k
CARD_G4 = [ 4,  8, None, 12, 15, 18, None, None, 25, 30, 40, 50, 22]    # 57 top; open threes/3k/4k
EMPTY   = [None] * 13


class BoxStrats(YahtzeeScene):
    def setup_scene(self):
        # Opens on the SAME empty card scene 10 ended on (LEFT_SC), present at
        # frame 1 with NO entrance — a seamless hard cut from 10's clear_to_card.
        self.card = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        self.add(self.card)          # present at frame 1 → seamless cut from scene 10
        self.board = DiceBoard()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _morph_to(self, target, run_time):
        """Transition the persistent card to `target` (a 13-row state) via the
        minimal set of cell changes; the card never moves/fades, so transition()'s
        cell-orphan caveat doesn't apply."""
        changes = {r: target[r] for r in range(13)
                   if self.card.value_nums.get(r) != target[r]}
        if changes:
            self.card.transition(self, changes, run_time=run_time)

    def _enter_dice(self, values, band):
        """Place the board's dice at `band` with `values` (opacity restored) and
        return FadeIn anims — dice ENTER here."""
        for i, d in enumerate(self.board.dice):
            d.set_value(values[i])
            d.set_opacity(1.0)
            d.move_to(slot_point(band, i))
        self.board.band = band
        self.board.slot = {i: i for i in range(5)}
        self.board.kept = []
        return [FadeIn(d, shift=DOWN * 0.4) for d in self.board.dice]

    def _first_roll(self, values):
        """Reset the board to band 0 (opacity restored) and return the FadeIn
        anims; caller then plays board.first_roll(values)."""
        self.board.place_initial(values)
        for d in self.board.dice:
            d.set_opacity(1.0)
        return [FadeIn(d) for d in self.board.dice]

    def _clear_dice(self):
        return [FadeOut(d) for d in self.board.dice]

    # ── a) intro: blank card (carried in) + guide lines ────────────────────────
    @subscene
    def intro(self):
        self.play(FadeIn(self.board.lines), run_time=0.8)

    # ── b) Chance — the rescue box (22345: twos→undo, lg straight→undo, chance) ─
    @subscene
    def chance(self):
        self._morph_to(CARD_B, run_time=1.1)
        self.play(*self._enter_dice([2, 2, 3, 4, 5], band=3), run_time=0.5)
        self.card.highlight_rows(self, [R_CHANCE], hold=1.0)

        # full fly-in, then REMOVE it (transition({row:None}) reverses bar+totals)
        self.card.upper(self, self.board.dice, 2)           # twos = 4
        self.wait(0.3)
        self._morph_to(CARD_B, run_time=0.6)                # undo the twos
        self.card.large_straight(self, self.board.dice)     # 22345 → scratch (0)
        self.wait(0.3)
        self._morph_to(CARD_B, run_time=0.6)                # undo the scratch
        self.card.chance(self, self.board.dice)             # chance = 16 (stays)

    # ── c) Yahtzee — don't chase it without a fallback (11123 → keep 123) ───────
    @subscene
    def yahtzee(self):
        self.play(*self._clear_dice(), run_time=0.3)
        self._morph_to(CARD_C, run_time=1.0)
        self.play(*self._first_roll([1, 1, 1, 2, 3]), run_time=0.4)
        self.play(*self.board.first_roll([1, 1, 1, 2, 3]), run_time=0.7)
        self.card.highlight_rows(self, [R_ONES], color=SCORE_RED, hold=1.0)
        # keep the 1-2-3 (partial straight) instead of the three 1s → go straight
        self.play(*self.board.show_keep([0, 3, 4], base_band=1), run_time=0.7)

    # ── d) Straights — 82% small straight on some first roll (montage of 5) ─────
    @subscene
    def straights(self):
        self.play(*self._clear_dice(), run_time=0.3)
        rolls = [[2, 5, 6, 2, 1], [6, 3, 6, 1, 4], [5, 2, 2, 6, 3],
                 [1, 1, 5, 4, 6], [4, 2, 1, 3, 1]]   # #5 = small straight {1,2,3,4}
        self.play(*self._enter_dice(rolls[0], band=1), run_time=0.4)
        for vals in rolls[1:]:
            morph_dice(self, self.board.dice, vals, run_time=0.45)
            self.wait(0.15)
        self.card.highlight_rows(self, [R_SMALL], hold=1.0)

    # ── e) Large straight — go for it when you have a fallback ──────────────────
    @subscene
    def large_straight(self):
        # example 1: sm+lg straight open; roll a small straight → keep 1234, go big
        self.play(*self._clear_dice(), run_time=0.3)
        self._morph_to(CARD_EA, run_time=1.0)
        self.play(*self._first_roll([1, 2, 3, 4, 1]), run_time=0.4)
        self.play(*self.board.first_roll([1, 2, 3, 4, 1]), run_time=0.7)
        self.card.highlight_rows(self, [R_LARGE, R_SMALL], hold=1.0)
        self.play(*self.board.show_keep([0, 1, 2, 3], base_band=1), run_time=0.7)

        # example 2: change to a card where sm straight is filled, chance is open;
        # roll 4-of-5 → keep 2346, go for large straight with chance as the safety
        self.play(*self._clear_dice(), run_time=0.3)
        self._morph_to(CARD_EB, run_time=1.0)
        self.play(*self._first_roll([2, 3, 4, 6, 6]), run_time=0.4)
        self.play(*self.board.first_roll([2, 3, 4, 6, 6]), run_time=0.7)
        self.card.highlight_rows(self, [R_LARGE, R_CHANCE], hold=1.0)
        self.play(*self.board.show_keep([0, 1, 2, 3], base_band=1), run_time=0.7)

    # ── f) Full house — usually comes on its own (three keep sequences) ─────────
    @subscene
    def full_house(self):
        self.play(*self._clear_dice(), run_time=0.3)
        self._morph_to(CARD_F, run_time=1.0)
        self.card.highlight_rows(self, [R_FH], hold=0.8)

        # seq 1: keep three 3's across two rerolls → 33345, fill Threes
        self.play(*self._first_roll([3, 3, 3, 2, 6]), run_time=0.4)
        self.play(*self.board.first_roll([3, 3, 3, 2, 6]), run_time=0.7)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([5, 1]), run_time=0.7)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([4, 5]), run_time=0.7)
        self.card.upper(self, self.board.dice, 3)           # Threes = 9

        # seq 2: keep three 2's → 22214 → 22224, fill Twos
        self.play(*self._clear_dice(), run_time=0.3)
        self.play(*self._first_roll([2, 2, 2, 5, 6]), run_time=0.4)
        self.play(*self.board.first_roll([2, 2, 2, 5, 6]), run_time=0.7)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([1, 4]), run_time=0.7)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([2, 4]), run_time=0.7)
        self.card.upper(self, self.board.dice, 2)           # Twos = 8

        # seq 3: keep three 1's → roll 5,5 → 11155 full house (fell into place)
        self.play(*self._clear_dice(), run_time=0.3)
        self.play(*self._first_roll([1, 1, 1, 3, 6]), run_time=0.4)
        self.play(*self.board.first_roll([1, 1, 1, 3, 6]), run_time=0.7)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([4, 2]), run_time=0.7)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([5, 5]), run_time=0.7)
        self.card.full_house(self, self.board.dice)         # Full House = 25

    # ── g) 3 & 4 of a kind — usually a top box; when forced, pick 4-kind ────────
    @subscene
    def kinds(self):
        self.play(*self._clear_dice(), run_time=0.3)
        self._morph_to(EMPTY, run_time=1.0)
        self.card.highlight_rows(self, [R_3KIND, R_4KIND], hold=1.0)

        # 55551 → four 5's belong in the TOP (Fives), not 4-of-a-kind
        self.play(*self._enter_dice([5, 5, 5, 5, 1], band=3), run_time=0.5)
        self.card.upper(self, self.board.dice, 5)           # Fives = 20

        # 55552 (2nd roll): keep 5's, roll a 3 → 55553 → only place left is 4-kind
        self.play(*self._clear_dice(), run_time=0.3)
        self.play(*self._first_roll([5, 5, 5, 5, 2]), run_time=0.4)
        self.play(*self.board.first_roll([5, 5, 5, 5, 2]), run_time=0.7)
        self.play(*self.board.keep([0, 1, 2, 3]), run_time=0.5)
        self.play(*self.board.roll_rest([3]), run_time=0.7)
        self.card.four_of_a_kind(self, self.board.dice)     # 4-of-a-Kind = 23

        # new card: 3k + 4k open; 44442 → fill 4-of-a-kind
        self.play(*self._clear_dice(), run_time=0.3)
        self._morph_to(CARD_G3, run_time=1.0)
        self.play(*self._enter_dice([4, 4, 4, 4, 2], band=3), run_time=0.5)
        self.card.four_of_a_kind(self, self.board.dice)     # 4-of-a-Kind = 18

        # new card: only 3k/4k/threes open; 12445 → forced, ZERO OUT 4-of-a-kind
        self.play(*self._clear_dice(), run_time=0.3)
        self._morph_to(CARD_G4, run_time=1.0)
        self.card.highlight_rows(self, [R_4KIND], color=SCORE_RED, hold=0.8)
        self.play(*self._enter_dice([1, 2, 4, 4, 5], band=3), run_time=0.5)
        self.card.four_of_a_kind(self, self.board.dice)     # scratch → 0
