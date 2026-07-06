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
FINAL_POS = [0, -0.8, 0]                     # where the final average lands
FINAL_SCALE = 2.6                            # how much the final average grows


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
    ``_setup_<name>()`` to build the mobjects it owns, then plays. Two voiceover
    beats get NO subscene (they play over the neighbouring holds): the "took days…
    simplify further" beat (empty animation column) and the "maximize average
    points" beat (nothing moves — the card stays LEFT, the number stays RIGHT).

    From b onward the scorecard sits on the LEFT and never moves back to centre;
    from c the number + caption appear on the RIGHT and STAY until the finale.
      two_cards          — two "same" scorecards
      one_card           — collapse to (filled, top, bottom, #yahtzees); card -> LEFT
      reduce_first       — number appears; 258.5T --log--> A  [Total -> Reduced]
      drop_yahtzee_count — yahtzee -> eligibility bit (empty/0/50)
      cap_top_at_63      — top score only matters below 63 (top-only edits)
      drop_bottom_total  — bottom score not needed at all
      reduce_second      — count the on-screen A down to C  [Reduced -> Final]
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

    def _setup_reduce_first(self):
        # c INTRODUCES the number: it fades in 258.5T, then counts to A. Number +
        # caption then STAY on the right, all the way through h.
        self._rf_start = self._num_text(SCENE1_POSITIONS, NUM_POS)
        self._rf_from = self._poslabel("Total positions:")
        self._rf_to = self._poslabel("Reduced positions:")

    def _setup_reduce_second(self):
        # h reuses the on-screen A number (self.num) and its caption; it just needs
        # the new caption to swap to.
        self._rs_to = self._poslabel("Final positions:")

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
        pos = [NUM_POS[i] + (FINAL_POS[i] - NUM_POS[i]) * mt for i in range(3)]
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

    def _count_to(self, start_static, start_val, end_val, from_label, to_label,
                  *, count, label_rt):
        """Count `start_static` (already on screen) from start_val to end_val on a
        log scale, fading `from_label` out EARLY (not kept around) and `to_label`
        in only AFTER the number lands. Leaves self.num / self.num_label at the end
        state. (The live counter is un-picklable, so it's built here.)"""
        tr = ValueTracker(math.log10(start_val))
        live = always_redraw(lambda: self._num_text(10 ** tr.get_value(), NUM_POS))
        self.remove(start_static)
        self.add(live)
        self.play(tr.animate.set_value(math.log10(end_val)),
                  from_label.animate(rate_func=_out_first).set_opacity(0.0),
                  run_time=count)
        self.remove(live, from_label)
        end_static = self._num_text(end_val, NUM_POS)
        self.add(end_static)
        self.play(FadeIn(to_label), run_time=label_rt)
        self.num, self.num_label = end_static, to_label

    # ══ subscenes (animation only) ═════════════════════════════════════════════
    # a) two "identical" scorecards
    @subscene
    def two_cards(self):
        self._setup_cards()
        in_rt, hold = 0.9, 1.0
        c1, c2 = self.card1, self.card2

        # entrance: both cards slide up from below (shared slide_in)
        self.play(c1.slide_in(self, from_dir=DOWN, play=False),
                  c2.slide_in(self, from_dir=DOWN, play=False), run_time=in_rt)

        # all filled boxes on BOTH at once, then Total row both, then top 3rd col both
        highlight(self, [self._box_target(c1, r) for r in FILLED_BOXES]
                        + [self._box_target(c2, r) for r in FILLED_BOXES], hold=hold)
        highlight(self, [self._total_target(c1), self._total_target(c2)], hold=hold)
        highlight(self, [self._summary_target(c1, "top"),
                         self._summary_target(c2, "top")], hold=hold)

    # b) collapse to the sufficient statistic; card settles on the LEFT (and stays
    #    there for the rest of the scene — the number/caption live on the right).
    @subscene
    def one_card(self):
        move_rt, hold = 0.9, 1.0
        c1 = self.card1
        self.play(FadeOut(self.card2, shift=RIGHT * 0.6),
                  c1.animate.move_to(CARD_L), run_time=move_rt)
        self.card2 = None

        highlight(self, [self._box_target(c1, r) for r in FILLED_BOXES], hold=hold)
        highlight(self, [self._summary_target(c1, "top")], hold=hold)
        highlight(self, [self._summary_target(c1, "bot")], hold=hold)
        highlight(self, [self._fullrow_target(c1, YAHTZEE_ROW)], hold=hold)

    # c) first reduction: introduce the number (258.5T) on the right, count to A.
    #    The number + caption STAY on screen from here through h.
    @subscene
    def reduce_first(self):
        self._setup_reduce_first()
        appear, count, label_rt, hold = 0.6, 2.4, 0.6, 0.6
        self.play(FadeIn(self._rf_start, shift=UP * 0.2),
                  FadeIn(self._rf_from, shift=UP * 0.2), run_time=appear)
        self.wait(hold)
        self._count_to(self._rf_start, SCENE1_POSITIONS, BLANK_A,
                       self._rf_from, self._rf_to, count=count, label_rt=label_rt)

    # (the "maximize average points" beat has no animation now — the card stays put
    #  on the left and the number stays on the right — so it gets no subscene.)

    # d) yahtzee count -> eligibility bit; crossfade empty/0/50 a few times
    @subscene
    def drop_yahtzee_count(self):
        self._setup_yahtzee_cycle()
        hold, cyc = 1.0, 0.22
        highlight(self, [self._fullrow_target(self.card1, YAHTZEE_ROW)], hold=hold)
        for zero, fifty in self.cyc_pairs:
            self.play(FadeIn(zero), run_time=cyc)
            self.play(FadeOut(zero), FadeIn(fifty), run_time=cyc)   # crossfade 0 -> 50
            self.play(FadeOut(fifty), run_time=cyc)

    # e) top score only matters below 63 — top-section-only edits (bottom untouched)
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
        # transition() adds new-value cell texts at SCENE level (orphaned from the
        # card group). Hard-swap the whole thing for a FRESH clean SCORES1 card
        # (identical → the instant swap is invisible): clear every top-level mobject
        # EXCEPT the persistent number + caption, then add the clean card (on the
        # LEFT), so nothing (card or orphan) is left behind.
        keep = {self.num, self.num_label}
        for m in list(self.mobjects):
            if m not in keep:
                self.remove(m)
        self.card1 = get_scorecard(center=CARD_L, scores=SCORES1)
        self.add(self.card1)

    # f) bottom score not needed at all
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

    # g) second reduction: count the on-screen A number down to C (Reduced -> Final).
    #    The card stays on the left; the number never left the screen.
    @subscene
    def reduce_second(self):
        self._setup_reduce_second()
        count, label_rt = 2.4, 0.6
        self._count_to(self.num, BLANK_A, BLANK_C,
                       self.num_label, self._rs_to, count=count, label_rt=label_rt)

    # h) replay scene-04's ending on THIS card: empty it box-by-box, the solver's
    #    avg-points-remaining climbing to ~254.6; the finale removes the card and
    #    moves + grows the number as it lands, then "Average total points:" appears.
    @subscene
    def perfect_average(self):
        self._setup_perfect_average()
        fade, appear, step_rt, count_rt, settle, last_rt, lbl_rt = \
            0.5, 0.7, 0.45, 0.55, 0.15, 2.0, 0.6
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
        # finale: drive the number's VALUE from the SAME tracker as its motion, so
        # it keeps COUNTING UP throughout the move-and-grow (two separate trackers
        # desync — the motion finishes while the value lags, so it looks like a
        # jump). Also removes the card and drops the caption early.
        v0, v1 = sweep[-2]["remaining"], sweep[-1]["remaining"]
        self.remove(live)
        fin = always_redraw(lambda: self._moving_ev(
            v0 + (v1 - v0) * move_t.get_value(), move_t.get_value()))
        self.add(fin)
        clutter = [m for m in self.mobjects if m is not fin and m is not self.ev_label]
        self.play(
            move_t.animate.set_value(1.0),
            *[FadeOut(m) for m in clutter],
            self.ev_label.animate(rate_func=_out_first).set_opacity(0.0),
            run_time=last_rt,
        )
        self.remove(fin, self.ev_label, *clutter)
        final = self._moving_ev(v1, 1.0)
        self.add(final)

        # only once everything has stopped: the caption appears above it
        avg = crisp_text("Average total points:", font_size=LABEL_FS, color=BLACK,
                         font=FONT, weight="BOLD").next_to(final, UP, buff=0.55)
        self.play(FadeIn(avg, shift=UP * 0.2), run_time=lbl_rt)
