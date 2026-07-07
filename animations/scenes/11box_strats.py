from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice, slot_point, BAND_YS

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
        self.card.COUNTER_LAG = 0.0        # bar counts IN SYNC with the box fill (no late race)
        self.add(self.card)
        self.board = DiceBoard()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _swap_card(self, scores, run_time, *, hold=None):
        """Fade the card's contents to a new pre-filled state. The new card fades
        IN over the OLD one (which stays fully solid underneath and is removed only
        once the new one is opaque) — so the identical FRAME never dips or ghosts
        ("the card crossfading into itself"); only the changed values + (63) bar
        visibly fade to their new state. No counting, no pop. A `hold` matching the
        current one stays solid across the fade; a fresh `hold` fades in."""
        old = self.card
        carry = hold is not None and set(hold) == set(old.held_rows())
        new = get_scorecard(center=LEFT_SC, scores=list(scores))
        new.COUNTER_LAG = 0.0
        self.add(new)                                  # ON TOP of the still-solid old card
        anims = [FadeIn(new)]                           # only the new card fades in
        anims += [FadeOut(d) for d in self.board.dice if d in self.mobjects]
        if carry:
            new.hold_rows_instant(self, hold)
        else:
            old._held = None
            if hold is not None:
                anims += new.hold_rows_anims(hold)
        self.play(*anims, run_time=run_time)
        keep = {new, self.board.lines}                 # drop the old card (now hidden) + orphans
        for f, b in new.held_pieces():
            keep.add(f); keep.add(b)
        for m in list(self.mobjects):
            if m not in keep:
                self.remove(m)
        old._held = None
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

    def _fade_dice(self, run_time):
        # Re-track every die first: some flourishes (FlashFill's `become`, used by
        # the small-straight preview) drop dice from the scene's top-level list, so
        # a plain `d in self.mobjects` filter would miss them and fade only one.
        self.add(*self.board.dice)
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=run_time)

    def _end_beat(self, dice_rt, rel_rt):
        """Close a beat: fade the dice out, THEN drop the persistent highlight."""
        self._fade_dice(dice_rt)
        self.card.release_rows(self, run_time=rel_rt)

    # ── a) intro: blank card (carried in) + guide lines. No highlight. ─────────
    @subscene
    def intro(self):
        self.play(FadeIn(self.board.lines), run_time=0.8)

    # ── b) Chance — the rescue box (22345: twos→undo, lg straight→undo, chance) ─
    @subscene
    def chance(self):
        self._swap_card(CARD_B, run_time=0.6, hold=[R_CHANCE])   # highlight rises WITH swap
        self.play(*self._enter_dice([2, 2, 3, 4, 5], band=3), run_time=0.4)

        self.card.upper(self, self.board.dice, 2)              # twos = 4 (full fly-in)
        self.wait(0.3)
        self.card.transition(self, {R_TWOS: None}, run_time=0.6)   # …then remove it
        self.card.large_straight(self, self.board.dice)        # 22345 → scratch
        self.wait(0.3)
        self.card.transition(self, {R_LARGE: None}, run_time=0.6)  # …then remove it
        self.card.chance(self, self.board.dice)                # chance = 16 (stays)

        self._end_beat(0.3, 0.3)                               # dice out, then drop highlight LAST

    # ── c) Yahtzee — don't chase it without a fallback (11123 → keep 123) ───────
    @subscene
    def yahtzee(self):
        self._swap_card(CARD_C, run_time=0.6, hold=[R_YAHT])   # Yahtzee lit WITH swap, whole beat
        self.play(*self._first_roll_entrance([1, 1, 1, 2, 3]), run_time=0.4)
        self.play(*self.board.first_roll([1, 1, 1, 2, 3]), run_time=0.7)
        self.card.highlight_rows(self, [R_ONES], color=SCORE_RED, hold=1.0)  # don't dump 1s
        self.play(*self.board.show_keep([0, 3, 4], base_band=1), run_time=0.7)  # keep 1-2-3
        self._end_beat(0.3, 0.3)

    # ── d) Straights — 82% small straight on some first roll (montage of 5) ─────
    @subscene
    def straights(self):
        self._swap_card(EMPTY, run_time=0.6, hold=[R_SMALL, R_LARGE])   # both straights, w/ swap
        self.wait(0.4)
        self.card.release_rows(self, [R_LARGE], run_time=0.3)  # drop large, keep small

        # first roll ROLLS; the rest are quick MORPHS with a hold so each is readable
        self.play(*self._first_roll_entrance([2, 5, 6, 2, 1]), run_time=0.4)
        self.play(*self.board.first_roll([2, 5, 6, 2, 1]), run_time=0.7)
        self.wait(0.5)
        for vals in ([6, 3, 6, 1, 4], [5, 2, 2, 6, 3], [1, 1, 5, 4, 6]):
            morph_dice(self, self.board.dice, vals, run_time=0.4)
            self.wait(0.6)
        morph_dice(self, self.board.dice, [4, 2, 1, 3, 1], run_time=0.4)   # #5 = small straight
        self.wait(0.3)
        # rearrange + flash colors, NO scoring
        self.card.small_straight(self, self.board.dice, y=BAND_YS[1], score=False)
        self._end_beat(0.4, 0.3)                               # remove dice, THEN drop small

    # ── e) Large straight — go for it when you have a fallback (NO rerolls) ─────
    @subscene
    def large_straight(self):
        # example 1: sm + lg open. Large lit from the start; show dice, then light
        # small, then push the keep forward (no rolling).
        self._swap_card(CARD_EA, run_time=0.6, hold=[R_LARGE])
        self.play(*self._enter_dice([1, 2, 3, 4, 1], band=1), run_time=0.4)
        self.card.extend_hold(self, [R_SMALL], run_time=0.35)  # small lit through the push
        self.play(*self.board.show_keep([0, 1, 2, 3], base_band=1), run_time=0.7)
        self._fade_dice(0.3)
        self.card.release_rows(self, [R_SMALL], run_time=0.3)  # drop small (large stays)

        # example 2: change card (sm filled, chance open). Large re-raised WITH the
        # swap; show dice, light chance, push forward.
        self._swap_card(CARD_EB, run_time=0.6, hold=[R_LARGE])
        self.play(*self._enter_dice([2, 3, 4, 6, 6], band=1), run_time=0.4)
        self.card.extend_hold(self, [R_CHANCE], run_time=0.35) # chance lit through the push
        self.play(*self.board.show_keep([0, 1, 2, 3], base_band=1), run_time=0.7)
        self._fade_dice(0.3)
        self.card.release_rows(self, [R_CHANCE], run_time=0.3)  # chance out FIRST
        self.card.release_rows(self, [R_LARGE], run_time=0.3)   # then large straight

    # ── f) Full house — comes on its own (three sequences, top-row scored) ──────
    @subscene
    def full_house(self):
        self._swap_card(CARD_F, run_time=0.6, hold=[R_FH])     # full house lit WITH swap

        # seq 1 (third roll): 3 threes saved at band 2 → push up, roll the rest → top
        self.play(*self._enter_dice([3, 3, 3, 1, 6], band=2), run_time=0.4)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([4, 5]), run_time=0.7)               # → 33345
        self.card.upper(self, self.board.dice, 3)              # Threes = 9

        # seq 2 (2s): BOTH rerolls — first roll 3 twos at band 1, reroll to band 2
        # (22214), reroll again to band 3 (22224), fill from the top
        self._fade_dice(0.3)
        self.play(*self._enter_dice([2, 2, 2, 5, 6], band=1), run_time=0.4)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([1, 4]), run_time=0.7)               # → 22214 (band 2)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([2, 4]), run_time=0.7)               # → 22224 (band 3)
        self.card.upper(self, self.board.dice, 2)              # Twos = 8

        # seq 3 (third roll): 3 ones saved at band 2 → roll 5,5 → 11155 full house
        self._fade_dice(0.3)
        self.play(*self._enter_dice([1, 1, 1, 3, 6], band=2), run_time=0.4)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.5)
        self.play(*self.board.roll_rest([5, 5]), run_time=0.7)               # → 11155
        self.card.full_house(self, self.board.dice)            # Full House = 25 (fell in)

        self._end_beat(0.3, 0.3)

    # ── g) 3 & 4 of a kind — usually a top box; when forced, pick 4-kind ────────
    @subscene
    def kinds(self):
        self._swap_card(EMPTY, run_time=0.6, hold=[R_3KIND, R_4KIND])  # both lit WITH swap

        # 55551 in the TOP row → four 5's belong in Fives, not 4-of-a-kind
        self.play(*self._enter_dice([5, 5, 5, 5, 1], band=3), run_time=0.4)
        self.card.upper(self, self.board.dice, 5)              # Fives = 20

        # 55552 SECOND roll (band 2) → keep 5's, roll a 3 → 55553 → 4-kind (top)
        self._fade_dice(0.3)
        self.play(*self._enter_dice([5, 5, 5, 5, 2], band=2), run_time=0.4)
        self.play(*self.board.keep([0, 1, 2, 3]), run_time=0.5)
        self.play(*self.board.roll_rest([3]), run_time=0.7)                 # → 55553
        self.card.four_of_a_kind(self, self.board.dice)        # 4-of-a-Kind = 23

        # new card (3k/4k stay lit across the swap); 44442 in top row → fill 4-kind
        self._fade_dice(0.3)
        self._swap_card(CARD_G3, run_time=0.6, hold=[R_3KIND, R_4KIND])
        self.play(*self._enter_dice([4, 4, 4, 4, 2], band=3), run_time=0.4)
        self.card.four_of_a_kind(self, self.board.dice)        # 4-of-a-Kind = 18

        # new card; 12445 in top row → ZERO OUT 4-kind (forced)
        self._fade_dice(0.3)
        self._swap_card(CARD_G4, run_time=0.6, hold=[R_3KIND, R_4KIND])
        self.play(*self._enter_dice([1, 2, 4, 4, 5], band=3), run_time=0.4)
        self.card.four_of_a_kind(self, self.board.dice)        # scratch → 0
        self._end_beat(0.3, 0.3)
