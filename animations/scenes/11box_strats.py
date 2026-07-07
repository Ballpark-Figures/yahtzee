from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, slot_point, BAND_YS, RollDie

# ── Scorecard ROW indices (card order — yahtzee=11 sits ABOVE chance=12) ───────
R_ONES, R_TWOS, R_THREES, R_FOURS, R_FIVES, R_SIXES = range(6)
R_3KIND, R_4KIND, R_FH, R_SMALL, R_LARGE, R_YAHT, R_CHANCE = 6, 7, 8, 9, 10, 11, 12

# ── Illustrative pre-filled card states (14 = 13 rows + yahtzee bonus). ────────
# ALL VALUES ARE ILLUSTRATIVE game-states I chose (internally consistent, not
# sourced numbers). "57 top" states sum the top section to 57.
#          1s   2s   3s   4s   5s   6s   3k   4k   fh   ss   ls   yz   ch    yb
CARD_B  = [ 3, None,  9, 12, 15, 18, 17, None, 25, 30, None,  0, None, None]  # 57 top; open 2s/4k/lg/chance
CARD_C  = [ 3,  6,  9, 12, 15, 18, 20, 24, 25, None, 40, None, 22, None]      # 63 top; open sm/yahtzee
CARD_EA = [ 3,  6,  9, 12, 15, 18, 20, 24, 25, None, None, 50, 22, None]      # open sm + lg straight
CARD_EB = [ 3,  6,  9, 12, 15, 18, 20, 24, 25, 30, None, 50, None, None]      # sm filled; open lg + chance
CARD_F  = [None]*6 + [20, 24, None, 30, 40, 50, 22, None]                     # whole top open + full house
CARD_G3 = [ 5,  6,  9, 12, 15, 18, None, None, 25, 30, 40, 50, 22, None]      # open 3k + 4k
CARD_G4 = [ 4,  8, None, 12, 15, 18, None, None, 25, 30, 40, 50, 22, None]    # 57 top; open 3s/3k/4k
EMPTY   = [None] * 14


class BoxStrats(YahtzeeScene):
    def setup_scene(self):
        # Opens on the SAME empty card scene 10 ended on (LEFT_SC), present at
        # frame 1 with NO entrance — a seamless hard cut from 10's clear_to_card.
        self.card = get_scorecard(center=LEFT_SC, scores=list(EMPTY))
        self.add(self.card)
        self.board = DiceBoard()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _swap_card(self, scores, run_time):
        """Fade a fresh PRE-FILLED card in over the current one (bar already at its
        final state, so it never animates), then hard-clear the old card + any
        top-level value-text orphans the scoring methods left behind. Keeps only
        the new card and the guide lines. Dice are re-entered per beat."""
        new = get_scorecard(center=LEFT_SC, scores=list(scores))
        self.add(new)
        self.play(FadeIn(new),
                  *[FadeOut(d) for d in self.board.dice if d in self.mobjects],
                  run_time=run_time)
        for m in list(self.mobjects):
            if m is not new and m is not self.board.lines:
                self.remove(m)
        self.card = new

    def _enter_dice(self, values, band):
        """Place the dice at `band` with `values` (opacity restored) and return the
        FadeIn anims — dice APPEAR IN PLACE (mid-turn / shown-result states)."""
        for i, d in enumerate(self.board.dice):
            d.set_value(values[i])
            d.set_opacity(1.0)
            d.move_to(slot_point(band, i))
        self.board.band = band
        self.board.slot = {i: i for i in range(5)}
        self.board.kept = []
        return [FadeIn(d) for d in self.board.dice]

    def _first_roll_entrance(self, values):
        """Set the dice at band 0 (opacity restored) for a rolling first roll;
        return the FadeIn anims. Caller then plays board.first_roll(values)."""
        self.board.place_initial(values)
        for d in self.board.dice:
            d.set_opacity(1.0)
        return [FadeIn(d) for d in self.board.dice]

    def _reroll(self, values):
        """Roll every die in place at band 1 to new `values` (montage re-roll)."""
        return [RollDie(d, slot_point(1, i), values[i])
                for i, d in enumerate(self.board.dice)]

    def _clear_dice(self, run_time):
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=run_time)

    # ── a) intro: blank card (carried in) + guide lines. No highlight. ─────────
    @subscene
    def intro(self):
        self.play(FadeIn(self.board.lines), run_time=0.8)

    # ── b) Chance — the rescue box (22345: twos→undo, lg straight→undo, chance) ─
    @subscene
    def chance(self):
        self._swap_card(CARD_B, run_time=0.8)
        self.card.hold_rows(self, [R_CHANCE], run_time=0.35)   # lit FIRST, whole beat
        self.play(*self._enter_dice([2, 2, 3, 4, 5], band=3), run_time=0.4)

        self.card.upper(self, self.board.dice, 2)              # twos = 4 (full fly-in)
        self.wait(0.3)
        self.card.transition(self, {R_TWOS: None}, run_time=0.6)   # …then remove it
        self.card.large_straight(self, self.board.dice)        # 22345 → scratch
        self.wait(0.3)
        self.card.transition(self, {R_LARGE: None}, run_time=0.6)  # …then remove it
        self.card.chance(self, self.board.dice)                # chance = 16 (stays)

        self.card.release_rows(self, run_time=0.3)             # dropped LAST

    # ── c) Yahtzee — don't chase it without a fallback (11123 → keep 123) ───────
    @subscene
    def yahtzee(self):
        self._swap_card(CARD_C, run_time=0.8)
        self.card.hold_rows(self, [R_YAHT], run_time=0.35)     # Yahtzee lit whole beat
        self.play(*self._first_roll_entrance([1, 1, 1, 2, 3]), run_time=0.4)
        self.play(*self.board.first_roll([1, 1, 1, 2, 3]), run_time=0.7)
        self.card.highlight_rows(self, [R_ONES], color=SCORE_RED, hold=1.0)  # don't dump 1s
        self.play(*self.board.show_keep([0, 3, 4], base_band=1), run_time=0.7)  # keep 1-2-3
        self.card.release_rows(self, run_time=0.3)

    # ── d) Straights — 82% small straight on some first roll (montage of 5) ─────
    @subscene
    def straights(self):
        self._swap_card(EMPTY, run_time=0.8)                   # start empty
        self.card.hold_rows(self, [R_SMALL, R_LARGE], run_time=0.35)  # both straights
        self.wait(0.4)
        self.card.release_rows(self, [R_LARGE], run_time=0.3)  # drop large, keep small

        rolls = [[2, 5, 6, 2, 1], [6, 3, 6, 1, 4], [5, 2, 2, 6, 3],
                 [1, 1, 5, 4, 6], [4, 2, 1, 3, 1]]             # #5 = small straight {1,2,3,4}
        self.play(*self._first_roll_entrance(rolls[0]), run_time=0.4)
        self.play(*self.board.first_roll(rolls[0]), run_time=0.7)
        for vals in rolls[1:-1]:
            self.play(*self._reroll(vals), run_time=0.5)
            self.wait(0.1)
        self.play(*self._reroll(rolls[-1]), run_time=0.5)      # 42131
        # once we've got the 1234: rearrange + flash colors, NO scoring
        self.card.small_straight(self, self.board.dice, y=BAND_YS[1], score=False)
        self.card.release_rows(self, run_time=0.3)

    # ── e) Large straight — go for it when you have a fallback ──────────────────
    @subscene
    def large_straight(self):
        # example 1: sm + lg open; roll a small straight → keep 1234, go big
        self._swap_card(CARD_EA, run_time=0.8)
        self.card.hold_rows(self, [R_LARGE], run_time=0.35)    # large lit WHOLE beat
        self.card.extend_hold(self, [R_SMALL], run_time=0.35)  # + small during 12341
        self.play(*self._first_roll_entrance([1, 2, 3, 4, 1]), run_time=0.4)
        self.play(*self.board.first_roll([1, 2, 3, 4, 1]), run_time=0.7)
        self.play(*self.board.show_keep([0, 1, 2, 3], base_band=1), run_time=0.7)
        self.card.release_rows(self, [R_SMALL], run_time=0.3)  # drop small after ex 1

        # example 2: change card (sm filled, chance open); 4-of-5 → keep 2346
        self.card.release_rows(self, run_time=0.0)             # drop large before swap
        self._swap_card(CARD_EB, run_time=0.8)
        self.card.hold_rows(self, [R_LARGE], run_time=0.35)    # re-raise large
        self.card.extend_hold(self, [R_CHANCE], run_time=0.35) # + chance during 23466
        self.play(*self._first_roll_entrance([2, 3, 4, 6, 6]), run_time=0.4)
        self.play(*self.board.first_roll([2, 3, 4, 6, 6]), run_time=0.7)
        self.play(*self.board.show_keep([0, 1, 2, 3], base_band=1), run_time=0.7)
        self.card.release_rows(self, run_time=0.3)

    # ── f) Full house — comes on its own (three THIRD rolls, top-row scored) ────
    @subscene
    def full_house(self):
        self._swap_card(CARD_F, run_time=0.8)
        self.card.hold_rows(self, [R_FH], run_time=0.35)       # full house lit whole beat

        # dice START at band 2 (second row from top); push the saved dice forward,
        # roll the rest up to band 3 (TOP), then score from the top.
        self.play(*self._enter_dice([3, 3, 3, 1, 6], band=2), run_time=0.4)  # 3 threes saved
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([4, 5]), run_time=0.7)               # → 33345
        self.card.upper(self, self.board.dice, 3)              # Threes = 9

        self._clear_dice(0.3)
        self.play(*self._enter_dice([2, 2, 2, 1, 4], band=2), run_time=0.4)  # 3 twos saved
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([2, 4]), run_time=0.7)               # → 22224
        self.card.upper(self, self.board.dice, 2)              # Twos = 8

        self._clear_dice(0.3)
        self.play(*self._enter_dice([1, 1, 1, 3, 6], band=2), run_time=0.4)  # 3 ones saved
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([5, 5]), run_time=0.7)               # → 11155
        self.card.full_house(self, self.board.dice)            # Full House = 25 (fell in)

        self.card.release_rows(self, run_time=0.3)

    # ── g) 3 & 4 of a kind — usually a top box; when forced, pick 4-kind ────────
    @subscene
    def kinds(self):
        self._swap_card(EMPTY, run_time=0.8)
        self.card.hold_rows(self, [R_3KIND, R_4KIND], run_time=0.35)  # both lit whole beat

        # 55551 in the TOP row → four 5's belong in Fives, not 4-of-a-kind
        self.play(*self._enter_dice([5, 5, 5, 5, 1], band=3), run_time=0.4)
        self.card.upper(self, self.board.dice, 5)              # Fives = 20

        # 55552 SECOND roll (band 2) → keep 5's, roll a 3 → 55553 → 4-kind (top)
        self._clear_dice(0.3)
        self.play(*self._enter_dice([5, 5, 5, 5, 2], band=2), run_time=0.4)
        self.play(*self.board.keep([0, 1, 2, 3]), run_time=0.5)
        self.play(*self.board.roll_rest([3]), run_time=0.7)                  # → 55553
        self.card.four_of_a_kind(self, self.board.dice)        # 4-of-a-Kind = 23

        # new card: 3k + 4k open; 44442 in top row → fill 4-of-a-kind
        self._clear_dice(0.3)
        self.card.release_rows(self, run_time=0.0)
        self._swap_card(CARD_G3, run_time=0.8)
        self.card.hold_rows(self, [R_3KIND, R_4KIND], run_time=0.35)
        self.play(*self._enter_dice([4, 4, 4, 4, 2], band=3), run_time=0.4)
        self.card.four_of_a_kind(self, self.board.dice)        # 4-of-a-Kind = 18

        # new card: only 3s/3k/4k open, 57 top; 12445 in top row → ZERO OUT 4-kind
        self._clear_dice(0.3)
        self.card.release_rows(self, run_time=0.0)
        self._swap_card(CARD_G4, run_time=0.8)
        self.card.hold_rows(self, [R_3KIND, R_4KIND], run_time=0.35)
        self.play(*self._enter_dice([1, 2, 4, 4, 5], band=3), run_time=0.4)
        self.card.four_of_a_kind(self, self.board.dice)        # scratch → 0
        self.card.release_rows(self, run_time=0.3)
