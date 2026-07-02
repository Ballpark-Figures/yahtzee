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
FINAL_EV_VAL     = 254.5877227783203       # dp_cache "remaining"; scene-04 end
EV_START         = 0.0                     # cosmetic climb start for the recap

# ── the two example scorecards (col-2 fills; row order = SCORE_ROWS) ───────────
#   0-5 Ones..Sixes | 6 3ofK | 7 4ofK | 8 FH | 9 SmS | 10 LgS | 11 Yahtzee |
#   12 Chance | 13 yahtzee-bonus.  Both: top=9, bottom=24, total=33.
SCORES1 = [3, 6, None, None, None, None,  None, 12, None, None, None, None, 12, 0]
SCORES2 = [1, 8, None, None, None, None,  None,  0, None, None, None, None, 24, 0]

# beat cap_top_at_63 "top section examples" — Ones ALWAYS open; top total
# 53 -> 63 -> 93, same bottom as card1 (illustrative fills; box = face*count).
EX_TOP_53 = [None, 4,  9, 12, 10, 18,  None, 12, None, None, None, None, 12, 0]
EX_TOP_63 = [None, 8, 12, 16, 15, 12,  None, 12, None, None, None, None, 12, 0]
EX_TOP_93 = [None, 10, 12, 16, 25, 30, None, 12, None, None, None, None, 12, 0]

FILLED_BOXES = [0, 1, 7, 12]               # boxes filled on both cards
OPEN_BOTTOM  = [6, 8, 9, 10, 11]           # unfilled bottom rows
YAHTZEE_ROW  = 11

# ── layout ────────────────────────────────────────────────────────────────────
CARD_C = CENTER_SC                          # [0, 0, 0]
CARD_L = LEFT_SC                            # [-4.74, 0, 0]
TWO_L  = [-3.9, 0, 0]
TWO_R  = [3.9, 0, 0]
NUM_POS = [2.9, -0.2, 0]                    # big number, right of a left-sat card
LBL_POS = [2.9, 0.95, 0]                    # caption above the number
NUM_FS  = 36
NUM_MAXW = 7.4                              # cap the widest (258.5T) to the panel
LABEL_FS = 30


def _fmt(v):
    return f"{int(round(v)):,}"


# label crossfade rate funcs — label-1 out over the first ~45%, label-2 in over
# the last ~45%, so the two captions are never both fully visible.
def _out_first(t):
    return smooth(min(t / 0.45, 1.0))


def _in_last(t):
    return smooth(max((t - 0.55) / 0.45, 0.0))


class Reductions(YahtzeeScene):
    """Scene 05 — reducing the 259-trillion position count to something a
    computer can actually solve.

    Subscene bodies are ANIMATION ONLY: every subscene calls its
    ``_setup_<name>()`` to build the mobjects it owns, then plays. (The
    voiceover-only "took days… simplify further" beat has an empty animation
    column, so it gets NO subscene — it plays over the neighbouring holds.)
      two_cards          — two "same" scorecards
      one_card           — collapse to (filled, top, bottom, #yahtzees)
      reduce_first       — 258.5T  --log-->  A (79.6B)  [Total -> Reduced]
      maximize_points    — number out, card back to centre
      drop_yahtzee_count — yahtzee -> eligibility bit (empty/0/50)
      cap_top_at_63      — top score only matters below 63 (example cards)
      drop_bottom_total  — bottom score not needed at all
      reduce_second      — A  --log-->  C (405M)  [Reduced -> Final]
      perfect_average    — replay scene-04 end: avg remaining -> ~254.6
    """

    def setup_scene(self):
        # Nothing is on screen at frame 0 (scene 05 follows a talking head).
        pass

    # ══ construction helpers (each owned by a subscene, called at its start) ═══
    def _setup_cards(self):
        self.card1 = get_scorecard(center=TWO_L, scores=SCORES1)
        self.card2 = get_scorecard(center=TWO_R, scores=SCORES2)
        self.num = None         # the big right-side number (carried between beats)
        self.num_label = None   # its caption
        self.strike = None      # the bottom-total cross-out (beat -> reduce_second)

    def _build_count(self, start_val, end_val, label_from, label_to):
        self._c_start_val, self._c_end_val = start_val, end_val
        self._c_start = self._num_text(start_val, NUM_POS)
        self._c_end = self._num_text(end_val, NUM_POS)
        self._c_from = self._poslabel(label_from)
        self._c_to = self._poslabel(label_to).set_opacity(0.0)

    def _setup_reduce_first(self):
        self._build_count(SCENE1_POSITIONS, BLANK_A,
                          "Total positions:", "Reduced positions:")

    def _setup_reduce_second(self):
        self._build_count(BLANK_A, BLANK_C,
                          "Reduced positions:", "Final positions:")

    def _setup_examples(self):
        self.examples = [get_scorecard(center=CARD_C, scores=s)
                         for s in (EX_TOP_53, EX_TOP_63, EX_TOP_93)]

    def _setup_yahtzee_cycle(self):
        cell = self.card1.value_cells[YAHTZEE_ROW].get_center()
        fs = self.card1.font_size
        self.cyc_pairs = [
            (crisp_text("0", font_size=fs, color=BLACK, font=FONT).move_to(cell),
             crisp_text("50", font_size=fs, color=BLACK, font=FONT).move_to(cell))
            for _ in range(3)]

    def _setup_bottom_strike(self):
        bt = self.card1.bottom_total_text
        self.strike = Line(bt.get_left() + LEFT * 0.1, bt.get_right() + RIGHT * 0.1,
                           color=SCORE_RED, stroke_width=6)

    def _setup_perfect_average(self):
        self.empty_card = get_scorecard(center=CARD_L, scores=None)
        self.ev_label = crisp_text("Avg points remaining:", font_size=LABEL_FS,
                                   color=AVG_GREEN, font=FONT,
                                   weight="BOLD").move_to(LBL_POS)
        self.ev_final = self._ev_text(FINAL_EV_VAL, NUM_POS)

    # ══ small builders + highlight targets ═════════════════════════════════════
    def _num_text(self, value, pos, fs=NUM_FS, maxw=NUM_MAXW):
        s = value if isinstance(value, str) else _fmt(value)
        t = crisp_text(s, font_size=fs, color=BLACK, font=FONT, weight="BOLD")
        if t.width > maxw:
            t.scale_to_fit_width(maxw)
        return t.move_to(pos)

    def _poslabel(self, s, color=BLACK):
        return crisp_text(s, font_size=LABEL_FS, color=color, font=FONT,
                          weight="BOLD").move_to(LBL_POS)

    def _ev_text(self, v, pos):
        return crisp_text(f"{v:.1f}", font_size=NUM_FS, color=AVG_GREEN,
                          font=FONT, weight="BOLD").move_to(pos)

    def _summary_cells(self, card):
        """(top, bottom) 3rd-column summary rectangles of a scorecard."""
        vr = card.value_cells[0].get_right()[0]
        tall = [m for m in card.cells
                if isinstance(m, Rectangle) and not isinstance(m, RoundedRectangle)
                and m.get_center()[0] > vr + 0.05
                and m.height > 3.5 * card.cell_height]
        tall.sort(key=lambda m: -m.get_center()[1])
        return tall[0], tall[1]

    # highlight() targets: (center, width, height) regions — no mobject side effects
    def _box_target(self, card, row):
        left = card.label_cells[row].get_left()[0]
        right = card.value_cells[row].get_right()[0]
        y = card.value_cells[row].get_center()[1]
        return ([(left + right) / 2, y, 0], right - left, card.cell_height)

    def _fullrow_target(self, card, row):
        top, _ = self._summary_cells(card)
        left = card.label_cells[row].get_left()[0]
        right = top.get_right()[0]
        y = card.value_cells[row].get_center()[1]
        return ([(left + right) / 2, y, 0], right - left, card.cell_height)

    def _summary_target(self, card, which):
        top, bot = self._summary_cells(card)
        cell = top if which == "top" else bot
        return (cell.get_center(), cell.width, cell.height)

    def _total_target(self, card):
        top, _ = self._summary_cells(card)
        left = card.label_cells[0].get_left()[0]
        right = top.get_right()[0]
        y = card.total_text.get_center()[1]
        return ([(left + right) / 2, y, 0], right - left, card.cell_height * 1.18)

    def _run_count(self, *, move_first, appear, count, hold):
        """Shared animation for the two reduction beats: card to the left, the
        start number + 'from' caption appear, then a log-scale count to the end
        while the caption crossfades to the 'to' label. Leaves self.num /
        self.num_label at the end state. (The live counter is un-picklable, so it
        is built here, in the animation, not in setup.)"""
        self.play(self.card1.animate.move_to(CARD_L), run_time=move_first)
        self.play(FadeIn(self._c_start, shift=UP * 0.2),
                  FadeIn(self._c_from, shift=UP * 0.2), run_time=appear)
        self.wait(hold)

        tr = ValueTracker(math.log10(self._c_start_val))
        live = always_redraw(lambda: self._num_text(10 ** tr.get_value(), NUM_POS))
        self.remove(self._c_start)
        self.add(live, self._c_to)
        self.play(tr.animate.set_value(math.log10(self._c_end_val)),
                  self._c_from.animate(rate_func=_out_first).set_opacity(0.0),
                  self._c_to.animate(rate_func=_in_last).set_opacity(1.0),
                  run_time=count)
        self.remove(live, self._c_from)
        self.add(self._c_end)
        self.num, self.num_label = self._c_end, self._c_to

    # ══ subscenes (animation only) ═════════════════════════════════════════════
    # a) two "identical" scorecards
    @subscene
    def two_cards(self):
        self._setup_cards()
        in_rt, hold = 0.9, 1.0
        c1, c2 = self.card1, self.card2

        # entrance: build at home (setup), drop offscreen, rise back up
        h1, h2 = c1.get_center(), c2.get_center()
        c1.shift(DOWN * 8)
        c2.shift(DOWN * 8)
        self.add(c1, c2)
        self.play(c1.animate.move_to(h1), c2.animate.move_to(h2), run_time=in_rt)

        # all filled boxes on BOTH at once, then Total row both, then top 3rd col both
        highlight(self, [self._box_target(c1, r) for r in FILLED_BOXES]
                        + [self._box_target(c2, r) for r in FILLED_BOXES], hold=hold)
        highlight(self, [self._total_target(c1), self._total_target(c2)], hold=hold)
        highlight(self, [self._summary_target(c1, "top"),
                         self._summary_target(c2, "top")], hold=hold)

    # b) collapse to the sufficient statistic
    @subscene
    def one_card(self):
        move_rt, hold = 0.9, 1.0
        c1 = self.card1
        self.play(FadeOut(self.card2, shift=RIGHT * 0.6),
                  c1.animate.move_to(CARD_C), run_time=move_rt)
        self.card2 = None

        highlight(self, [self._box_target(c1, r) for r in FILLED_BOXES], hold=hold)
        highlight(self, [self._summary_target(c1, "top")], hold=hold)
        highlight(self, [self._summary_target(c1, "bot")], hold=hold)
        highlight(self, [self._fullrow_target(c1, YAHTZEE_ROW)], hold=hold)

    # c) first reduction: 258.5T --log--> A (Total -> Reduced)
    @subscene
    def reduce_first(self):
        self._setup_reduce_first()
        move_first, appear, count, hold = 0.9, 0.6, 2.4, 0.6
        self._run_count(move_first=move_first, appear=appear, count=count, hold=hold)

    # d) number out, card back to centre
    @subscene
    def maximize_points(self):
        fade_rt, move_rt = 0.6, 0.9
        self.play(FadeOut(self.num, shift=UP * 0.2),
                  FadeOut(self.num_label, shift=UP * 0.2), run_time=fade_rt)
        self.num = self.num_label = None
        self.play(self.card1.animate.move_to(CARD_C), run_time=move_rt)

    # e) yahtzee count -> eligibility bit; cycle empty/0/50 a few times
    @subscene
    def drop_yahtzee_count(self):
        self._setup_yahtzee_cycle()
        hold, cyc = 1.0, 0.22
        highlight(self, [self._fullrow_target(self.card1, YAHTZEE_ROW)], hold=hold)
        for zero, fifty in self.cyc_pairs:
            self.play(FadeIn(zero), run_time=cyc)
            self.play(ReplacementTransform(zero, fifty), run_time=cyc)
            self.play(FadeOut(fifty), run_time=cyc)

    # f) top score only matters below 63 — switch top-section examples
    @subscene
    def cap_top_at_63(self):
        self._setup_examples()
        tr_rt, gap, hold = 0.8, 0.35, 1.0
        for new in self.examples:
            self.play(ReplacementTransform(self.card1, new), run_time=tr_rt)
            self.card1 = new
            self.wait(gap)
        # …the only thing that matters is which boxes are still open (the 1's).
        highlight(self, [self._box_target(self.card1, 0)], hold=hold)

    # g) bottom score not needed at all
    @subscene
    def drop_bottom_total(self):
        self._setup_bottom_strike()
        strike_rt, hold = 0.5, 1.0
        self.play(Create(self.strike), run_time=strike_rt)
        highlight(self, [self._box_target(self.card1, r) for r in OPEN_BOTTOM],
                  hold=hold)

    # h) second reduction: A --log--> C (Reduced -> Final)
    @subscene
    def reduce_second(self):
        self._setup_reduce_second()
        fade, move_first, appear, count, hold = 0.5, 0.9, 0.6, 2.4, 0.5
        if self.strike is not None:
            self.play(FadeOut(self.strike), run_time=fade)
            self.strike = None
        self._run_count(move_first=move_first, appear=appear, count=count, hold=hold)

    # i) replay scene-04's ending: avg points remaining -> ~254.6
    @subscene
    def perfect_average(self):
        self._setup_perfect_average()
        fade, empty_rt, count_rt, move_rt = 0.5, 0.8, 1.6, 1.0
        self.play(FadeOut(self.num, shift=UP * 0.2),
                  FadeOut(self.num_label, shift=UP * 0.2), run_time=fade)
        self.num = self.num_label = None

        tr = ValueTracker(EV_START)
        live = always_redraw(lambda: self._ev_text(tr.get_value(), NUM_POS))
        self.play(ReplacementTransform(self.card1, self.empty_card),
                  FadeIn(self.ev_label, shift=UP * 0.2), run_time=empty_rt)
        self.card1 = self.empty_card
        self.add(live)
        self.play(tr.animate.set_value(FINAL_EV_VAL), run_time=count_rt)
        self.remove(live)
        self.add(self.ev_final)

        self.play(FadeOut(self.empty_card, shift=LEFT * 0.6), FadeOut(self.ev_label),
                  self.ev_final.animate.move_to(CENTER_SC).scale(1.9), run_time=move_rt)
