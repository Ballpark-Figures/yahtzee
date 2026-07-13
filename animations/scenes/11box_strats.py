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
# Ones FULL (per the script — the used Ones box is what gets highlighted red), but
# Fives left open so the top is INCOMPLETE (46) → neutral blue bar (a complete top
# under 63 renders the equally-distracting red "missed-bonus" fill). Varied counts,
# no par pattern. Fives (a face not in the 11123 roll) is the open box.
CARD_C  = [ 2,  8,  6, 12, None, 18, 20, 24, 25, None, 40, None, 22, None]    # 46 top, blue; open 5s/sm/yahtzee
CARD_EA = [ 2,  8,  6, 12, None, 18, 20, 24, 25, None, None, 50, 22, None]    # 46 top, blue; open 5s/sm/lg
CARD_EB = [ 2,  8,  6, 12, None, 18, 20, 24, 25, 30, None, 50, None, None]    # 46 top, blue; open 5s/lg/chance
CARD_F  = [None]*6 + [20, 24, None, 30, 40, 50, 22, None]                     # whole top open + full house
CARD_G3 = [ 2,  8,  6, 12, None, 18, None, None, 25, 30, 40, 50, 22, None]    # top unfinished (Fives open→blue, no bonus); Fours FULL (used→44442 goes to 4-kind); open 3k+4k
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
    def _swap_card(self, scores, run_time, *, hold=None, keep_dice=False, lead=None):
        """Change the card to a new pre-filled `scores` state IN PLACE (SAME card
        mobject) — no crossfade, so the frame never dips and nothing ghosts. Diffs
        the current cells against `scores` and routes the changes through
        `card.transition`, folding the highlight change + the dice into that ONE
        play via transition's `extra`:
          • `hold` = the rows highlighted AFTER the change — rows dropped from the
            current hold are released, newly-held rows raised, both in the play.
          • dice: faded out WITH the change, unless `keep_dice` (carry them on) or a
            `lead` is given (e.g. a dice regroup+morph to co-play with the change).
        (Was: build a fresh card and crossfade it over the old one — that reintroduced
        the very ghosting `transition` exists to avoid. See scene 06 for the in-place
        refill-one/open-next idiom this now matches.)"""
        card = self.card
        # cell diff → the minimal changes to reach `scores` (rows 0..12; no scene-11
        # state touches the yahtzee bonus at index 13)
        changes = {row: scores[row] for row in range(13)
                   if card.value_nums.get(row) != scores[row]}
        # hold diff → release rows no longer held, raise newly-held rows (folded in)
        target_hold = set(hold or [])
        cur_hold = set(card.held_rows())
        rel_anims, rel_mobs = card.release_rows_anims(sorted(cur_hold - target_hold))
        extra = rel_anims + card.hold_rows_anims(sorted(target_hold - cur_hold))
        # dice: a caller `lead` (e.g. a transform) wins; else fade them unless kept
        if lead:
            extra += list(lead)
        elif not keep_dice:
            extra += [FadeOut(d) for d in self.board.dice if d in self.mobjects]
        card.transition(self, changes, run_time=run_time, extra=extra)
        for m in rel_mobs:
            self.remove(m)

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

    def _carry_dice_anims(self, values, band):
        """TRANSFORM the current dice into a new flat `band` roll instead of fading
        them out and re-entering: each die slides into its flat `band` slot AND
        morphs its face to `values` in ONE Transform (regroup + morph together).
        Returns (anims, commit): play `anims` (optionally WITH something else, e.g.
        the card swap), then call commit() to re-sync die values/positions + the
        board to that flat band. Carrying dice between rolls is the scene-04/06
        idiom; doing it as one move+morph lets it ride the card swap."""
        anims = []
        for i, d in enumerate(self.board.dice):
            tgt = d.copy()
            tgt.set_value(values[i])
            tgt.set_opacity(1.0)
            tgt.move_to(slot_point(band, i))
            anims.append(Transform(d, tgt))

        def commit():
            for i, d in enumerate(self.board.dice):        # re-sync (visual no-op)
                d.set_value(values[i])
                d.set_opacity(1.0)
                d.move_to(slot_point(band, i))
            self.board.band = band
            self.board.slot = {i: i for i in range(5)}
            self.board.kept = []

        return anims, commit

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
        self.wait(0.5)
        self.play(*self._enter_dice([2, 2, 3, 4, 5], band=3), run_time=0.4)

        self.wait(3.6)
        self.card.upper(self, self.board.dice, 2, run_time=1.0)              # twos = 4 (full fly-in)
        self.card.transition(self, {R_TWOS: None}, run_time=0.6)   # …then remove it
        self.card.large_straight(self, self.board.dice, run_time=1.8)        # 22345 → scratch
        #self.wait(0.3)
        self.card.transition(self, {R_LARGE: None}, run_time=0.6)  # …then remove it
        self.card.chance(self, self.board.dice, run_time=0.8)                # chance = 16 (stays)
        self.wait(2.0)
        self._end_beat(0.3, 0.3)                               # dice out, then drop highlight LAST

    # ── c) Yahtzee — don't chase it without a fallback (11123 → keep 123) ───────
    @subscene
    def yahtzee(self):
        self._swap_card(CARD_C, run_time=0.6, hold=[R_YAHT])   # Yahtzee lit WITH swap, whole beat
        self.wait(3.0)
        self.play(*self._first_roll_entrance([1, 1, 1, 2, 3]), run_time=0.4)
        self.wait(0.5)
        self.play(*self.board.first_roll([1, 1, 1, 2, 3]), run_time=0.7)
        self.wait(0.5)
        self.card.highlight_rows(self, [R_ONES], color=SCORE_RED, hold=1.0)  # don't dump 1s
        self.wait(0.5)
        self.play(*self.board.show_keep([0, 3, 4], base_band=1), run_time=0.7)  # keep 1-2-3
        self.wait(0.5)
        self._end_beat(0.3, 0.3)

    # ── d) Straights — 82% small straight on some first roll (montage of 5) ─────
    @subscene
    def straights(self):
        self._swap_card(EMPTY, run_time=0.6, hold=[R_SMALL, R_LARGE])   # both straights, w/ swap
        self.wait(0.2)
        self.card.release_rows(self, [R_LARGE], run_time=0.3)  # drop large, keep small

        # first roll ROLLS; the rest are quick MORPHS with a hold so each is readable
        self.play(*self._first_roll_entrance([2, 5, 6, 2, 1]), run_time=0.4)
        self.play(*self.board.first_roll([2, 5, 6, 2, 1]), run_time=0.7)
        self.wait(0.2)
        for vals in ([6, 3, 6, 1, 4], [5, 2, 2, 6, 3], [1, 1, 5, 4, 6]):
            morph_dice(self, self.board.dice, vals, run_time=0.4)
            self.wait(0.3)
        morph_dice(self, self.board.dice, [4, 2, 1, 3, 1], run_time=0.4)   # #5 = small straight
        self.wait(0.3)
        # rearrange + flash colors, SCORE it, then remove the score right after
        self.card.small_straight(self, self.board.dice, y=BAND_YS[1], score=True)
        self.card.transition(self, {R_SMALL: None}, run_time=0.6)   # …then remove it
        self._end_beat(0.4, 0.3)                               # remove dice, THEN drop small

    # ── e) Large straight — go for it when you have a fallback (NO rerolls) ─────
    @subscene
    def large_straight(self):
        # example 1: sm + lg open. Large lit from the start; show dice, then light
        # small, then push the keep forward (no rolling).
        self._swap_card(CARD_EA, run_time=0.6, hold=[R_LARGE])
        self.wait(3.0)
        self.play(*self._enter_dice([1, 2, 3, 4, 1], band=1), run_time=0.4)
        self.card.extend_hold(self, [R_SMALL], run_time=0.35)  # small lit through the push
        self.play(*self.board.show_keep([0, 1, 2, 3], base_band=1), run_time=0.7)
        self.card.release_rows(self, [R_SMALL], run_time=0.3)  # drop small (dice STAY — carried to ex 2)

        # example 2: change card (sm filled, chance open). Large re-raised WITH the
        # swap. Rather than fade the dice out + re-enter, carry the SAME dice over —
        # and transition them (slide back into a flat line + morph to the new roll,
        # in one move) DURING the card swap by riding it as the swap's `lead`.
        self.wait(1.0)
        dice_xf, commit_dice = self._carry_dice_anims([2, 3, 4, 6, 6], band=1)
        self._swap_card(CARD_EB, run_time=0.6, hold=[R_LARGE], keep_dice=True,
                        lead=dice_xf)
        commit_dice()
        self.card.extend_hold(self, [R_CHANCE], run_time=0.35) # chance lit through the push
        self.play(*self.board.show_keep([0, 1, 2, 3], base_band=1), run_time=0.7)
        self.wait(2.0)
        self._fade_dice(0.3)
        self.card.release_rows(self, [R_CHANCE], run_time=0.3)  # chance out FIRST
        self.wait(3.0)
        self.card.release_rows(self, [R_LARGE], run_time=0.3)   # then large straight

    # ── f) Full house — comes on its own (three sequences, top-row scored) ──────
    @subscene
    def full_house(self):
        self._swap_card(CARD_F, run_time=0.6, hold=[R_FH])     # full house lit WITH swap

        # seq 1 (third roll): 3 threes saved at band 2 → push up, roll the rest → top
        self.play(*self._enter_dice([3, 3, 3, 1, 6], band=2), run_time=0.4)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.4)
        self.play(*self.board.roll_rest([4, 5]), run_time=0.4)               # → 33345
        #self.card.upper(self, self.board.dice, 3)              # Threes = 9

        # seq 2 (2s): BOTH rerolls — first roll 3 twos at band 1, reroll to band 2
        # (22214), reroll again to band 3 (22224), fill from the top
        self._fade_dice(0.2)
        self.play(*self._enter_dice([2, 2, 2, 5, 6], band=1), run_time=0.2)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.4)
        self.play(*self.board.roll_rest([1, 4]), run_time=0.4)               # → 22214 (band 2)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.4)
        self.play(*self.board.roll_rest([2, 4]), run_time=0.4)               # → 22224 (band 3)
        #self.card.upper(self, self.board.dice, 2)              # Twos = 8

        # seq 3 (third roll): 3 ones saved at band 2 → roll 5,5 → 11155 full house
        self._fade_dice(0.2)
        self.play(*self._enter_dice([1, 1, 1, 3, 6], band=2), run_time=0.2)
        self.play(*self.board.keep([0, 1, 2]), run_time=0.4)
        self.play(*self.board.roll_rest([5, 5]), run_time=0.4)               # → 11155
        self.card.full_house(self, self.board.dice)            # Full House = 25 (fell in)

        self._end_beat(0.3, 0.3)

    # ── g) 3 & 4 of a kind — usually a top box; when forced, pick 4-kind ────────
    @subscene
    def kinds(self):
        self._swap_card(EMPTY, run_time=0.6, hold=[R_3KIND, R_4KIND])  # both lit WITH swap

        # 55551 in the TOP row → four 5's belong in Fives, not 4-of-a-kind
        self.wait(1.5)
        self.play(*self._enter_dice([5, 5, 5, 5, 1], band=3), run_time=0.4)
        self.card.upper(self, self.board.dice, 5)              # Fives = 20

        # 55552 SECOND roll (band 2) → keep 5's, roll a 3 → 55553 → 4-kind (top)
        self.wait(2.0)
        self._fade_dice(0.3)
        self.play(*self._enter_dice([5, 5, 5, 5, 2], band=2), run_time=0.4)
        self.play(*self.board.keep([0, 1, 2, 3]), run_time=0.5)
        self.play(*self.board.roll_rest([3]), run_time=0.7)                 # → 55553
        self.card.four_of_a_kind(self, self.board.dice)        # 4-of-a-Kind = 23

        # new card (3k/4k stay lit across the swap); 44442 in top row → fill 4-kind
        self.wait(2.5)
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
