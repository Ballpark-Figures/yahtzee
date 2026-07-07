from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import get_die
from assets.first_turn_data import first_turn_outcomes
from bpkfigures.scroll_list import ScrollList

# math category indices (constants.py order): 0-5 Ones..Sixes
ONES, TWOS, THREES, FOURS, FIVES, SIXES = range(6)
THREE_KIND, FOUR_KIND, FULL_HOUSE = 6, 7, 8
SMALL_STRAIGHT, LARGE_STRAIGHT, CHANCE, YAHTZEE = 9, 10, 11, 12

# ── Wheel geometry (scorecard on the left at LEFT_SC, list on the right) ────────
# wheel centre x is computed at runtime (centred between the card + frame edge)
BOX_X, PTS_X, DICE_X, AVG_X = -4.4, -0.7, 1.9, 4.4   # column x's within a row
FS = 30.0                      # wheel text size
DIE = 0.40                     # mini-die size
GAP = 0.88                     # wheel centre-to-centre spacing


def make_row(o):
    """One list row: Box | Points | mini dice | Avg total. Columns pinned at
    fixed local x. Every cell's cap/digit band is aligned to a common top (via a
    reference '0') so ascenders/descenders — e.g. the 'p' in 'pts' — don't make
    one column sit higher than the next; the dice centre on that same band."""
    box = crisp_text(o["box"], font_size=FS, color=BLACK)
    unit = "pt" if o["points"] == 1 else "pts"
    pts = crisp_text(f"{o['points']} {unit}", font_size=FS, color=BLACK)
    dice = VGroup(*[get_die(v, size=DIE) for v in o["dice"]]).arrange(RIGHT, buff=0.05)
    avg = crisp_text(f"{o['ev']:.1f}", font_size=FS, color=ACCENT_FILL)
    ref = crisp_text("0", font_size=FS)               # digit-band reference (y=0)
    box.move_to([BOX_X + box.width / 2, 0, 0]).align_to(ref, UP)   # left edge pinned
    pts.move_to([PTS_X, 0, 0]).align_to(ref, UP)
    avg.move_to([AVG_X - avg.width / 2, 0, 0]).align_to(ref, UP)   # right edge pinned
    dice.move_to([DICE_X, 0, 0])
    return VGroup(box, pts, dice, avg)


class FirstTurn(YahtzeeScene):
    def setup_scene(self):
        self.data = first_turn_outcomes()["outcomes"]
        self.card = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        # Centre the wheel + title in the gap between the card and the frame edge.
        wheel_cx = (self.card.get_right()[0] + config.frame_x_radius) / 2
        rows = [make_row(o) for o in self.data]
        self.wheel = ScrollList(rows, focus=0, radius=3, gap=GAP,
                                center=[wheel_cx, 0, 0])
        # Build small + scale to width so the long caption stays ONE line
        # (crisp_text wraps a long string at font_size >= ~24; see CLAUDE.md).
        self.title = crisp_text("Average Points After First Turn", font_size=14,
                                color=BLACK)
        self.title.scale_to_fit_width(6.4).move_to([wheel_cx, 3.75, 0])

    # ── helpers ────────────────────────────────────────────────────────────────
    def _idx(self, cat, points):
        return next(i for i, o in enumerate(self.data)
                    if o["cat"] == cat and o["points"] == points)

    def _fill(self, sc_row, value, *, hold=0.5):
        """A transient gold flash of the box + its number (number only exists
        during the flash)."""
        self.card.flash_rows(self, [(sc_row, value)], hold=hold)

    # ── beats ────────────────────────────────────────────────────────────────
    @subscene
    def bring_card(self):
        # a) bring back the empty scorecard (shared slide-in entrance)
        self.card.slide_in(self, run_time=1.0)

    @subscene
    def yahtzee_first(self):
        # b) fill+highlight Yahtzee; show ONLY the first list row + title
        self.wheel.set_focus(0)
        self.wheel.hide_all()
        self.add(self.wheel)
        self.play(self.wheel.fade_in([0]), FadeIn(self.title), run_time=1.0)
        self._fill(11, 50, hold=0.6)

    @subscene
    def scroll_top(self):
        # c) fade in the rest, scroll through Sixes24 -> Threes12 one at a time
        self.play(self.wheel.fade_in(), run_time=0.8)
        for idx in [self._idx(SIXES, 24), self._idx(FIVES, 20),
                    self._idx(LARGE_STRAIGHT, 40), self._idx(FOURS, 16),
                    self._idx(THREES, 12)]:
            o = self.data[idx]
            self.play(self.wheel.scroll_to(idx), run_time=1.0)
            self._fill(o["sc_row"], o["points"], hold=0.4)

    @subscene
    def three_of_number(self):
        # d) scroll to the first "3 of a number" (three 6s -> Sixes 18)
        idx = self._idx(SIXES, 18)
        o = self.data[idx]
        self.play(self.wheel.scroll_to(idx), run_time=1.2)
        self._fill(o["sc_row"], o["points"], hold=0.5)

    @subscene
    def full_house(self):
        # e) scroll to full house
        idx = self._idx(FULL_HOUSE, 25)
        o = self.data[idx]
        self.play(self.wheel.scroll_to(idx), run_time=1.2)
        self._fill(o["sc_row"], o["points"], hold=0.5)

    @subscene
    def straights(self):
        # f) large straight, then small straight
        for cat, pts in [(LARGE_STRAIGHT, 40), (SMALL_STRAIGHT, 30)]:
            idx = self._idx(cat, pts)
            o = self.data[idx]
            self.play(self.wheel.scroll_to(idx), run_time=1.2)
            self._fill(o["sc_row"], o["points"], hold=0.5)

    @subscene
    def two_or_fewer(self):
        # g) no scroll; transient RED demos of bad placements (black numbers flash
        # in sync with the highlight, then vanish — committed fill untouched)
        self.card.flash_rows(self, [(3, 8), (4, 10), (5, 12)],
                             color=SCORE_RED, hold=0.8)              # two 4s/5s/6s
        self.card.flash_rows(self, [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6)],
                             color=SCORE_RED, hold=0.8)              # 23456 singles

    @subscene
    def four_kind(self):
        # h) never fill 4-of-a-kind
        self.card.flash_rows(self, [(7, None)], color=SCORE_RED, hold=0.9)

    @subscene
    def three_kind(self):
        # i) flag the 3kind box red, scroll to a 3kind example, then a NORMAL
        # (default gold) flash for the one we'd actually use
        self.card.flash_rows(self, [(6, None)], color=SCORE_RED, hold=0.6)
        idx = self._idx(THREE_KIND, 28)
        self.play(self.wheel.scroll_to(idx), run_time=1.2)
        self.card.flash_rows(self, [(6, 28)], hold=0.8)   # default (gold)

    @subscene
    def worst(self):
        # j) scroll all the way to the bottom (Chance 19 / 23446)
        idx = self._idx(CHANCE, 19)
        o = self.data[idx]
        self.play(self.wheel.scroll_to(idx), run_time=2.0)
        self._fill(o["sc_row"], o["points"], hold=0.6)

    @subscene
    def clear_to_card(self):
        # k) Fade the list + title, leaving the (already-empty) scorecard at
        # LEFT_SC so scene 11 opens on the same card — seamless hard cut.
        self.play(FadeOut(self.wheel), FadeOut(self.title), run_time=1.0)
