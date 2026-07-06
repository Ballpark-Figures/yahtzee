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
WHEEL_CX = 3.4                 # wheel centre x
BOX_X, PTS_X, DICE_X, AVG_X = -3.6, -0.7, 1.2, 3.6   # column x's within a row
FS = FONT_SIZE_SM
DIE = 0.26


def make_row(o):
    """One list row: Box | Points | mini dice | Avg total. Columns pinned at
    fixed local x so they align when a row is centred."""
    box = crisp_text(o["box"], font_size=FS)
    pts = crisp_text(str(o["points"]), font_size=FS)
    dice = VGroup(*[get_die(v, size=DIE) for v in o["dice"]]).arrange(RIGHT, buff=0.04)
    avg = crisp_text(f"{o['ev']:.1f}", font_size=FS, color=ACCENT_FILL)
    box.move_to([BOX_X + box.width / 2, 0, 0])       # left edge pinned
    pts.move_to([PTS_X, 0, 0])
    dice.move_to([DICE_X, 0, 0])
    avg.move_to([AVG_X - avg.width / 2, 0, 0])        # right edge pinned
    return VGroup(box, pts, dice, avg)


class FirstTurn(YahtzeeScene):
    def setup_scene(self):
        self.data = first_turn_outcomes()["outcomes"]
        self.card = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        rows = [make_row(o) for o in self.data]
        self.wheel = ScrollList(rows, focus=0, radius=3, gap=0.72,
                                center=[WHEEL_CX, 0, 0])
        self.title = crisp_text("Average Points After First Turn", font_size=FS)
        self.title.move_to([WHEEL_CX, 3.6, 0])
        self._cur_num = None

    # ── helpers ────────────────────────────────────────────────────────────────
    def _idx(self, cat, points):
        return next(i for i, o in enumerate(self.data)
                    if o["cat"] == cat and o["points"] == points)

    def _fill_anims(self, sc_row, value, color=BLACK):
        """Anims to show `value` in the scorecard box, clearing the previous
        'current' fill. Returns the anims so the caller can play them alongside a
        scroll."""
        num = crisp_text(str(value), font_size=SCORECARD_FONT_SIZE, color=color)
        num.move_to(self.card.value_cells[sc_row].get_center())
        anims = [FadeIn(num)]
        if self._cur_num is not None:
            anims.append(FadeOut(self._cur_num))
        self._cur_num = num
        return anims

    def _flash_bad(self, items, *, hold=0.7):
        """Transient red demo: flash the given scorecard rows red (with optional
        numbers), then remove — WITHOUT touching the committed 'current' fill.
        `items` = [(sc_row, value_or_None), ...]."""
        nums = []
        for sc_row, value in items:
            if value is not None:
                n = crisp_text(str(value), font_size=SCORECARD_FONT_SIZE,
                               color=SCORE_RED)
                n.move_to(self.card.value_cells[sc_row].get_center())
                nums.append(n)
        if nums:
            self.play(*[FadeIn(n) for n in nums], run_time=0.3)
        self.card.highlight_rows(self, [r for r, _ in items], color=SCORE_RED,
                                 hold=hold)
        if nums:
            self.play(*[FadeOut(n) for n in nums], run_time=0.3)

    def _reveal_neighbors(self, run_time):
        """Fade in the wheel rows that are visible at the current focus but were
        hidden (used after showing only the first entry)."""
        pos = self.wheel._pos_value
        anims = []
        for i, r in enumerate(self.wheel.rows):
            if i == round(pos):
                continue
            t = self.wheel._opacity_of(i - pos)
            if t > 0.01:
                r.set_opacity(t)
                anims.append(FadeIn(r))
        self.play(*anims, run_time=run_time)

    # ── beats ──────────────────────────────────────────────────────────────────
    @subscene
    def bring_card(self):
        # a) bring back the empty scorecard (slide up, per the card-entrance rule)
        rt = 1.0
        self.card.shift(DOWN * 9)
        self.play(self.card.animate.move_to(LEFT_SC), run_time=rt)

    @subscene
    def yahtzee_first(self):
        # b) fill+highlight Yahtzee; show ONLY the first list row + title
        rt = 1.0
        self.wheel.set_focus(0)
        for r in self.wheel.rows:
            r.set_opacity(0)
        self.add(self.wheel)
        r0 = self.wheel.rows[0]
        r0.set_opacity(1.0)
        self.play(FadeIn(r0), FadeIn(self.title),
                  *self._fill_anims(11, 50), run_time=rt)
        self.card.highlight_rows(self, [11], color=SCORE_GREEN, hold=0.6)

    @subscene
    def scroll_top(self):
        # c) fade in the rest, scroll through Sixes24 -> Threes12 one at a time
        self._reveal_neighbors(run_time=0.8)
        step_rt = 1.2
        for idx in [self._idx(SIXES, 24), self._idx(FIVES, 20),
                    self._idx(LARGE_STRAIGHT, 40), self._idx(FOURS, 16),
                    self._idx(THREES, 12)]:
            o = self.data[idx]
            self.play(self.wheel.scroll_to(idx),
                      *self._fill_anims(o["sc_row"], o["points"]), run_time=step_rt)
            self.card.highlight_rows(self, [o["sc_row"]], color=SCORE_GREEN, hold=0.4)

    @subscene
    def three_of_number(self):
        # d) scroll to the first "3 of a number" (three 6s -> Sixes 18)
        rt = 1.5
        idx = self._idx(SIXES, 18)
        o = self.data[idx]
        self.play(self.wheel.scroll_to(idx),
                  *self._fill_anims(o["sc_row"], o["points"]), run_time=rt)
        self.card.highlight_rows(self, [o["sc_row"]], color=SCORE_GREEN, hold=0.5)

    @subscene
    def full_house(self):
        # e) scroll to full house
        rt = 1.5
        idx = self._idx(FULL_HOUSE, 25)
        o = self.data[idx]
        self.play(self.wheel.scroll_to(idx),
                  *self._fill_anims(o["sc_row"], o["points"]), run_time=rt)
        self.card.highlight_rows(self, [o["sc_row"]], color=SCORE_GREEN, hold=0.5)

    @subscene
    def straights(self):
        # f) large straight, then small straight
        rt = 1.5
        for cat, pts in [(LARGE_STRAIGHT, 40), (SMALL_STRAIGHT, 30)]:
            idx = self._idx(cat, pts)
            o = self.data[idx]
            self.play(self.wheel.scroll_to(idx),
                      *self._fill_anims(o["sc_row"], o["points"]), run_time=rt)
            self.card.highlight_rows(self, [o["sc_row"]], color=SCORE_GREEN, hold=0.5)

    @subscene
    def two_or_fewer(self):
        # g) no scroll; transient red demos of bad placements
        self._flash_bad([(3, 8), (4, 10), (5, 12)], hold=0.8)          # two 4s/5s/6s
        self._flash_bad([(1, 2), (2, 3), (3, 4), (4, 5), (5, 6)], hold=0.8)  # 23456 singles

    @subscene
    def four_kind(self):
        # h) never fill 4-of-a-kind
        self._flash_bad([(7, None)], hold=0.9)

    @subscene
    def three_kind(self):
        # i) highlight 3kind red, scroll to a 3kind example, transient fill
        self._flash_bad([(6, None)], hold=0.6)
        rt = 1.5
        idx = self._idx(THREE_KIND, 28)
        self.play(self.wheel.scroll_to(idx), run_time=rt)
        self._flash_bad([(6, 28)], hold=0.8)

    @subscene
    def worst(self):
        # j) scroll all the way to the bottom (Chance 19 / 23446)
        rt = 2.0
        idx = self._idx(CHANCE, 19)
        o = self.data[idx]
        self.play(self.wheel.scroll_to(idx),
                  *self._fill_anims(o["sc_row"], o["points"]), run_time=rt)
        self.card.highlight_rows(self, [o["sc_row"]], color=SCORE_GREEN, hold=0.6)
