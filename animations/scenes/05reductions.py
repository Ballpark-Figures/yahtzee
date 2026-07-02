from pathlib import Path
import sys
import math

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard


# ── the numbers (all SOURCED — see the scene-05 provenance report) ────────────
#   start : scene 01's final figure (258.5 trillion YAHTZEE positions)
#   A     : first reduction  = 105,285,166 non-terminal GameStates      x 756
#   C     : second reduction = 536,320 non-terminal ReducedGameStates   x 756
#   EV    : perfect-play average, scene 04's ending value (254.5877…)
SCENE1_POSITIONS = 258_521_977_812_672
BLANK_A          = 79_595_585_496          # math/count_game_states.py
BLANK_C          = 405_457_920             # math/count_reduced_states.py
FINAL_EV         = "254.6"                 # exact 254.5877; dp_cache "remaining"

# ── the two example scorecards (col-2 fills; row order = SCORE_ROWS) ───────────
#   0-5 Ones..Sixes | 6 3ofK | 7 4ofK | 8 FH | 9 SmS | 10 LgS | 11 Yahtzee |
#   12 Chance | 13 yahtzee-bonus.  Both: top=9, bottom=24, total=33.
SCORES1 = [3, 6, None, None, None, None,  None, 12, None, None, None, None, 12, 0]
SCORES2 = [1, 8, None, None, None, None,  None,  0, None, None, None, None, 24, 0]

FILLED_BOXES  = [0, 1, 7, 12]              # boxes filled on both cards
OPEN_BOTTOM   = [6, 8, 9, 10, 11]          # unfilled bottom rows on card1
YAHTZEE_ROW   = 11

# ── layout ────────────────────────────────────────────────────────────────────
CARD_C = CENTER_SC                          # [0, 0, 0]
CARD_L = LEFT_SC                            # [-4.74, 0, 0]
TWO_L  = [-3.9, 0, 0]
TWO_R  = [3.9, 0, 0]
NUM_POS = [2.9, 0, 0]                       # big number, right of a left-sat card
NUM_FS  = 30
NUM_MAXW = 6.6                              # cap the widest (258.5T) to the panel
HL = ACCENT_GOLD                            # "notice this" highlight colour


def _fmt(v):
    return f"{int(round(v)):,}"


class Reductions(YahtzeeScene):
    """Scene 05 — reducing the 259-trillion position count to something a
    computer can actually solve.

    Beats (— in the script's two columns):
      two_cards           — two "same" scorecards
      one_card            — collapse to (filled, top, bottom, #yahtzees)
      reduce_first        — 258.5T  --log-->  A (79.6B)
      computers_eventually— pure-VO hold ("took days… simplify further")
      maximize_points     — number out, card back to centre
      drop_yahtzee_count  — yahtzee -> eligibility bit (empty/0/50)
      cap_top_at_63       — top score only matters below 63
      drop_bottom_total   — bottom score not needed at all
      reduce_second       — A  --log-->  C (405M)
      perfect_average     — perfect-play average, ~254.6
    """

    def setup_scene(self):
        # Nothing is on screen at frame 0 (scene 05 follows a talking head).
        pass

    # ── owned mobjects ────────────────────────────────────────────────────────
    def _setup_cards(self):
        self.card1 = get_scorecard(center=TWO_L, scores=SCORES1)
        self.card2 = get_scorecard(center=TWO_R, scores=SCORES2)
        self.num = None       # the big right-side number (carried between beats)
        self.strike = None    # the bottom-section cross-out (beat h -> i)

    # ── number helpers (log-scale counter, scene-01 model) ────────────────────
    def _num_text(self, value, pos, fs=NUM_FS, maxw=NUM_MAXW):
        s = value if isinstance(value, str) else _fmt(value)
        t = crisp_text(s, font_size=fs, color=BLACK, font=FONT, weight="BOLD")
        if t.width > maxw:
            t.scale_to_fit_width(maxw)
        t.move_to(pos)
        return t

    def _count_down(self, start_static, start, end, pos, *, run_time, fs=NUM_FS):
        """Swap `start_static` for a live log-scale counter, tick it down to
        `end`, then leave a static end number (returned). always_redraw is
        removed before the subscene ends so the snapshot stays picklable."""
        tr = ValueTracker(math.log10(start))
        live = always_redraw(
            lambda: self._num_text(10 ** tr.get_value(), pos, fs))
        self.remove(start_static)
        self.add(live)
        self.play(tr.animate.set_value(math.log10(end)), run_time=run_time)
        self.remove(live)
        end_static = self._num_text(end, pos, fs)
        self.add(end_static)
        return end_static

    # ── a) two "identical" scorecards ─────────────────────────────────────────
    @subscene
    def two_cards(self):
        self._setup_cards()
        in_rt, hl_rt = 0.9, 0.8
        c1, c2 = self.card1, self.card2

        # rise in together from below
        h1, h2 = c1.get_center(), c2.get_center()
        c1.shift(DOWN * 8)
        c2.shift(DOWN * 8)
        self.add(c1, c2)
        self.play(c1.animate.move_to(h1), c2.animate.move_to(h2), run_time=in_rt)

        # same boxes filled -> same top section (9) on both
        for c in (c1, c2):
            c.highlight_rows(self, FILLED_BOXES, color=HL, opacity=0.5,
                             run_time=hl_rt, lag_ratio=0.1)
        for c in (c1, c2):
            c.highlight_rows(self, range(6), color=HL, opacity=0.45,
                             run_time=hl_rt)

    # ── b) collapse to the sufficient statistic ───────────────────────────────
    @subscene
    def one_card(self):
        move_rt, hl_rt = 0.9, 0.8
        c1 = self.card1
        self.play(FadeOut(self.card2, shift=RIGHT * 0.6),
                  c1.animate.move_to(CARD_C), run_time=move_rt)
        self.card2 = None

        # which boxes filled -> top score -> bottom score -> yahtzee row
        c1.highlight_rows(self, FILLED_BOXES, color=HL, opacity=0.5,
                          run_time=hl_rt, lag_ratio=0.1)
        c1.highlight_rows(self, range(6), color=HL, opacity=0.45, run_time=hl_rt)
        c1.highlight_rows(self, range(6, 13), color=HL, opacity=0.45, run_time=hl_rt)
        c1.highlight_rows(self, [YAHTZEE_ROW], color=HL, opacity=0.5, run_time=hl_rt)

    # ── c) first reduction: 258.5T --log--> A ─────────────────────────────────
    @subscene
    def reduce_first(self):
        move_rt, appear_rt, count_rt, hold = 0.9, 0.7, 2.2, 0.6
        self.play(self.card1.animate.move_to(CARD_L), run_time=move_rt)
        start = self._num_text(SCENE1_POSITIONS, NUM_POS)
        self.play(FadeIn(start, shift=UP * 0.2), run_time=appear_rt)
        self.wait(hold)
        self.num = self._count_down(start, SCENE1_POSITIONS, BLANK_A, NUM_POS,
                                    run_time=count_rt)

    # ── d) pure-VO hold ("took days… simplify further"); col 2 is empty ───────
    @subscene
    def computers_eventually(self):
        hold = 2.2   # tunable: the beat's whole length; A lingers on screen
        self.wait(hold)

    # ── e) number out, card back to centre ────────────────────────────────────
    @subscene
    def maximize_points(self):
        fade_rt, move_rt = 0.6, 0.9
        self.play(FadeOut(self.num, shift=UP * 0.2), run_time=fade_rt)
        self.num = None
        self.play(self.card1.animate.move_to(CARD_C), run_time=move_rt)

    # ── f) yahtzee count -> eligibility bit (empty / 0 / 50) ───────────────────
    @subscene
    def drop_yahtzee_count(self):
        hl_rt, cyc_rt, hold = 0.8, 0.5, 0.4
        c = self.card1
        c.highlight_rows(self, [YAHTZEE_ROW], color=HL, opacity=0.5, run_time=hl_rt)

        cell = c.value_cells[YAHTZEE_ROW]
        zero = crisp_text("0", font_size=c.font_size, color=BLACK,
                          font=FONT).move_to(cell.get_center())
        fifty = crisp_text("50", font_size=c.font_size, color=BLACK,
                           font=FONT).move_to(cell.get_center())
        self.play(FadeIn(zero), run_time=cyc_rt)
        self.wait(hold)
        self.play(ReplacementTransform(zero, fifty), run_time=cyc_rt)
        self.wait(hold)
        self.play(FadeOut(fifty), run_time=cyc_rt)

    # ── g) top score only matters below 63 (63 vs 93, Ones open) ──────────────
    @subscene
    def cap_top_at_63(self):
        hl_rt, cyc_rt, hold = 0.8, 0.6, 0.4
        c = self.card1
        c.highlight_rows(self, range(6), color=HL, opacity=0.4, run_time=hl_rt)

        # top-section total callout, right of the top rows: <63 -> 63 -> 93.
        top_y = c.value_cells[2].get_center()[1]
        pos = [c.get_right()[0] + 1.0, top_y, 0]

        def _cap(s):
            return crisp_text(s, font_size=NUM_FS, color=ACCENT_FILL,
                              font=FONT, weight="BOLD").move_to(pos)

        t = _cap("55")
        self.play(FadeIn(t, shift=UP * 0.15), run_time=cyc_rt)
        self.wait(hold)
        t2 = _cap("63")
        self.play(ReplacementTransform(t, t2), run_time=cyc_rt)
        self.wait(hold)
        t3 = _cap("93")
        self.play(ReplacementTransform(t2, t3), run_time=cyc_rt)
        self.wait(hold)

        # only which boxes are still open matters -> highlight the open one (1's)
        c.highlight_rows(self, [0], color=HL, opacity=0.5, run_time=hl_rt)
        self.play(FadeOut(t3, shift=UP * 0.15), run_time=cyc_rt)

    # ── h) bottom score not needed at all ─────────────────────────────────────
    @subscene
    def drop_bottom_total(self):
        strike_rt, hl_rt = 0.6, 0.8
        c = self.card1

        # cross out the whole bottom section (a diagonal strike)
        tl = c.label_cells[6].get_corner(UL)
        br = c.value_cells[12].get_corner(DR)
        self.strike = Line(tl, br, color=SCORE_RED, stroke_width=6)
        self.play(Create(self.strike), run_time=strike_rt)

        # …once we know which boxes are open, we have everything we need
        c.highlight_rows(self, OPEN_BOTTOM, color=HL, opacity=0.5,
                         run_time=hl_rt, lag_ratio=0.1)

    # ── i) second reduction: A --log--> C ─────────────────────────────────────
    @subscene
    def reduce_second(self):
        fade_rt, move_rt, appear_rt, count_rt, hold = 0.5, 0.9, 0.6, 2.2, 0.5
        c = self.card1
        if self.strike is not None:
            self.play(FadeOut(self.strike), run_time=fade_rt)
            self.strike = None
        self.play(c.animate.move_to(CARD_L), run_time=move_rt)

        start = self._num_text(BLANK_A, NUM_POS)
        self.play(FadeIn(start, shift=UP * 0.2), run_time=appear_rt)
        self.wait(hold)
        self.num = self._count_down(start, BLANK_A, BLANK_C, NUM_POS,
                                    run_time=count_rt)

    # ── j) perfect-play average, ~254.6 (stub for scene-04 end replay) ────────
    @subscene
    def perfect_average(self):
        fade_rt, appear_rt, move_rt, hold = 0.6, 0.8, 1.0, 0.5
        # STUB: the script says "replay end of previous scene"; here we just
        # reveal the perfect-play average that scene 04 climbs to.
        self.play(FadeOut(self.num, shift=UP * 0.2), run_time=fade_rt)
        self.num = None

        ev = self._num_text(FINAL_EV, NUM_POS)
        self.play(FadeIn(ev, shift=UP * 0.2), run_time=appear_rt)
        self.wait(hold)

        # remove card, move the number to centre and enlarge
        self.play(FadeOut(self.card1, shift=LEFT * 0.6),
                  ev.animate.move_to(CENTER_SC).scale(1.8), run_time=move_rt)
