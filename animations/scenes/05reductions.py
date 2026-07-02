from pathlib import Path
import sys
import math

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets import reductions_data as rd


# ── the numbers (all SOURCED — see the scene-05 provenance report) ────────────
#   start : scene 01's final figure (258.5 trillion YAHTZEE positions)
#   A     : first reduction  = 105,285,166 non-terminal GameStates      x 756
#   C     : second reduction = 536,320 non-terminal ReducedGameStates   x 756
#   EV    : beat i's sweep comes from the solver (assets/reductions_data.py)
SCENE1_POSITIONS = 258_521_977_812_672
BLANK_A          = 79_595_585_496          # math/count_game_states.py
BLANK_C          = 405_457_920             # math/count_reduced_states.py

# ── the two example scorecards (col-2 fills; row order = SCORE_ROWS) ───────────
#   0-5 Ones..Sixes | 6 3ofK | 7 4ofK | 8 FH | 9 SmS | 10 LgS | 11 Yahtzee |
#   12 Chance | 13 yahtzee-bonus.  Both: top=9, bottom=24, total=33.
SCORES1 = [3, 6, None, None, None, None,  None, 12, None, None, None, None, 12, 0]
SCORES2 = [1, 8, None, None, None, None,  None,  0, None, None, None, None, 24, 0]

# beat cap_top_at_63 — top-section-only edits (scorecard rows 0-5); the bottom
# section is NEVER touched. Ones always open; top total 53 -> 63 -> 93. Applied
# to the live card with transition(), so only the top cells + top summary move.
EX_TOPS = [
    {0: None, 1: 4,  2: 9,  3: 12, 4: 10, 5: 18},   # 53
    {1: 8,  2: 12, 3: 16, 4: 15, 5: 12},            # 63
    {1: 10, 2: 12, 3: 16, 4: 25, 5: 30},            # 93
]
RESTORE_TOP = {0: 3, 1: 6, 2: None, 3: None, 4: None, 5: None}   # back to SCORES1

FILLED_BOXES = [0, 1, 7, 12]               # boxes filled on both cards
OPEN_BOTTOM  = [6, 8, 9, 10, 11]           # unfilled bottom rows
YAHTZEE_ROW  = 11

# solver category (reductions_data) → scorecard row (differ only at 11/12)
_SC_BOX = {11: 12, 12: 11}


def _sc_box(solver_cat):
    return _SC_BOX.get(solver_cat, solver_cat)


# ── layout ────────────────────────────────────────────────────────────────────
CARD_C = CENTER_SC                          # [0, 0, 0]
CARD_L = LEFT_SC                            # [-4.74, 0, 0]
TWO_L  = [-3.9, 0, 0]
TWO_R  = [3.9, 0, 0]
NUM_POS = [2.85, -0.15, 0]                  # big number, right of a left-sat card
LBL_POS = [2.85, 1.2, 0]                    # caption above the number
NUM_FS  = 46
NUM_MAXW = 9.0                              # cap the widest (258.5T) to the panel
LABEL_FS = 38
FINAL_SCALE = 1.6                           # how much the final average grows


def _fmt(v):
    return f"{int(round(v)):,}"


# fade the OLD caption out over the first ~45% of the count (so it isn't kept
# around); the new caption appears only AFTER the number lands.
def _out_first(t):
    return smooth(min(t / 0.45, 1.0))


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
      cap_top_at_63      — top score only matters below 63 (top-only edits)
      drop_bottom_total  — bottom score not needed at all
      reduce_second      — A  --log-->  C (405M)  [Reduced -> Final]
      perfect_average    — replay scene-04 end: empty the card box-by-box, the
                           solver's avg-points-remaining climbs to 254.6
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
        self.strike = None      # the bottom-total cross-out (built + cleared in g)

    def _build_count(self, start_val, end_val, label_from, label_to):
        self._c_start_val, self._c_end_val = start_val, end_val
        self._c_start = self._num_text(start_val, NUM_POS)
        self._c_end = self._num_text(end_val, NUM_POS)
        self._c_from = self._poslabel(label_from)
        self._c_to = self._poslabel(label_to)          # added only after the count

    def _setup_reduce_first(self):
        self._build_count(SCENE1_POSITIONS, BLANK_A,
                          "Total positions:", "Reduced positions:")

    def _setup_reduce_second(self):
        self._build_count(BLANK_A, BLANK_C,
                          "Reduced positions:", "Final positions:")

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
        self.sweep = rd.scene05_numbers()["sweep"]   # solver avg-points-remaining
        self.ev_label = crisp_text("Avg points remaining:", font_size=LABEL_FS,
                                   color=BLACK, font=FONT,
                                   weight="BOLD").move_to(LBL_POS)

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
        return crisp_text(f"{v:.1f}", font_size=NUM_FS, color=BLACK,
                          font=FONT, weight="BOLD").move_to(pos)

    def _moving_ev(self, v, mt, fs=NUM_FS):
        """The avg-points number, interpolated from its right-side spot toward the
        centre and grown by `mt` in [0, 1] (for the finale move)."""
        t = crisp_text(f"{v:.1f}", font_size=fs, color=BLACK, font=FONT,
                       weight="BOLD")
        pos = [NUM_POS[i] + (CENTER_SC[i] - NUM_POS[i]) * mt for i in range(3)]
        return t.move_to(pos).scale(1 + (FINAL_SCALE - 1) * mt)

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

    def _run_count(self, *, move_first, appear, count, label_rt, hold):
        """Shared animation for the two reduction beats: card to the left, the
        start number + 'from' caption appear, then a log-scale count to the end.
        The 'from' caption fades out EARLY during the count (not kept around); the
        'to' caption appears only AFTER the number lands. Leaves self.num /
        self.num_label at the end state. (The live counter is un-picklable, so it
        is built here, in the animation, not in setup.)"""
        self.play(self.card1.animate.move_to(CARD_L), run_time=move_first)
        self.play(FadeIn(self._c_start, shift=UP * 0.2),
                  FadeIn(self._c_from, shift=UP * 0.2), run_time=appear)
        self.wait(hold)

        tr = ValueTracker(math.log10(self._c_start_val))
        live = always_redraw(lambda: self._num_text(10 ** tr.get_value(), NUM_POS))
        self.remove(self._c_start)
        self.add(live)
        self.play(tr.animate.set_value(math.log10(self._c_end_val)),
                  self._c_from.animate(rate_func=_out_first).set_opacity(0.0),
                  run_time=count)
        self.remove(live, self._c_from)
        self.add(self._c_end)

        # number has landed — only NOW bring in the new caption
        self.play(FadeIn(self._c_to), run_time=label_rt)
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
        move_first, appear, count, label_rt, hold = 0.9, 0.6, 2.4, 0.6, 0.6
        self._run_count(move_first=move_first, appear=appear, count=count,
                        label_rt=label_rt, hold=hold)

    # d) number out, card back to centre
    @subscene
    def maximize_points(self):
        fade_rt, move_rt = 0.6, 0.9
        self.play(FadeOut(self.num, shift=UP * 0.2),
                  FadeOut(self.num_label, shift=UP * 0.2), run_time=fade_rt)
        self.num = self.num_label = None
        self.play(self.card1.animate.move_to(CARD_C), run_time=move_rt)

    # e) yahtzee count -> eligibility bit; crossfade empty/0/50 a few times
    @subscene
    def drop_yahtzee_count(self):
        self._setup_yahtzee_cycle()
        hold, cyc = 1.0, 0.22
        highlight(self, [self._fullrow_target(self.card1, YAHTZEE_ROW)], hold=hold)
        for zero, fifty in self.cyc_pairs:
            self.play(FadeIn(zero), run_time=cyc)
            self.play(FadeOut(zero), FadeIn(fifty), run_time=cyc)   # crossfade 0 -> 50
            self.play(FadeOut(fifty), run_time=cyc)

    # f) top score only matters below 63 — top-section-only edits (bottom untouched)
    @subscene
    def cap_top_at_63(self):
        edit_rt, gap, hold, restore_rt = 0.8, 0.35, 1.0, 0.8
        for changes in EX_TOPS:
            self.card1.transition(self, changes, run_time=edit_rt)
            self.wait(gap)
        # …only which boxes are still open matters (the 1's) —
        highlight(self, [self._box_target(self.card1, 0)], hold=hold)
        # — then restore the top section to its earlier state.
        self.card1.transition(self, RESTORE_TOP, run_time=restore_rt)

    # g) bottom score not needed at all
    @subscene
    def drop_bottom_total(self):
        self._setup_bottom_strike()
        strike_rt, strike_hold, unstrike_rt, hold = 0.5, 0.5, 0.4, 1.0
        # cross out the bottom total, let it register, then REMOVE the cross-out…
        self.play(Create(self.strike), run_time=strike_rt)
        self.wait(strike_hold)
        self.play(FadeOut(self.strike), run_time=unstrike_rt)
        self.strike = None
        # …then highlight the open bottom boxes (all we actually need).
        highlight(self, [self._box_target(self.card1, r) for r in OPEN_BOTTOM],
                  hold=hold)

    # h) second reduction: A --log--> C (Reduced -> Final)
    @subscene
    def reduce_second(self):
        self._setup_reduce_second()
        move_first, appear, count, label_rt, hold = 0.9, 0.6, 2.4, 0.6, 0.5
        self._run_count(move_first=move_first, appear=appear, count=count,
                        label_rt=label_rt, hold=hold)

    # i) replay scene-04's ending on THIS card: empty it box-by-box, the solver's
    #    avg-points-remaining climbing to ~254.6; the finale removes the card and
    #    moves + grows the number as it lands, then "Average Points:" appears.
    @subscene
    def perfect_average(self):
        self._setup_perfect_average()
        fade, appear, step_rt, count_rt, settle, last_rt, lbl_rt = \
            0.5, 0.7, 0.45, 0.55, 0.15, 1.2, 0.5
        sweep = self.sweep

        self.play(FadeOut(self.num, shift=UP * 0.2),
                  FadeOut(self.num_label, shift=UP * 0.2), run_time=fade)
        self.num = self.num_label = None

        # expected points remaining for the current (end-of-h) card
        start = self._ev_text(sweep[0]["remaining"], NUM_POS)
        self.play(FadeIn(self.ev_label, shift=UP * 0.2),
                  FadeIn(start, shift=UP * 0.2), run_time=appear)
        self.wait(0.3)

        tr = ValueTracker(sweep[0]["remaining"])
        move_t = ValueTracker(0.0)
        live = always_redraw(lambda: self._moving_ev(tr.get_value(), move_t.get_value()))
        self.remove(start)
        self.add(live)

        # empty the card one box at a time (all but the last), re-reading the EV
        for step in sweep[1:-1]:
            self.card1.transition(self, {_sc_box(step["emptied"]): None},
                                  run_time=step_rt)
            self.play(tr.animate.set_value(step["remaining"]), run_time=count_rt)
            self.wait(settle)

        # finale: the last count — remove the card, move + grow the number, and
        # drop the "Avg points remaining:" caption right away. Fade EVERYTHING
        # except the moving number: the card group plus any summary texts
        # transition() left at scene level (a bare FadeOut(card1) misses those).
        last = sweep[-1]["remaining"]
        clutter = [m for m in self.mobjects if m is not live and m is not self.ev_label]
        self.play(
            tr.animate.set_value(last),
            move_t.animate.set_value(1.0),
            *[FadeOut(m) for m in clutter],
            self.ev_label.animate(rate_func=_out_first).set_opacity(0.0),
            run_time=last_rt,
        )
        self.remove(live, self.ev_label, *clutter)
        final = self._moving_ev(last, 1.0)
        self.add(final)

        # only once everything has stopped: "Average Points:" appears
        avg = crisp_text("Average Points:", font_size=LABEL_FS, color=BLACK,
                         font=FONT, weight="BOLD").next_to(final, UP, buff=0.45)
        self.play(FadeIn(avg, shift=UP * 0.2), run_time=lbl_rt)
