from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice
from bpkfigures.histogram import get_histogram


# ── Scene 06 — the last turn ──────────────────────────────────────────────────
# For EACH box: if it's the only box left open on the last turn, what's the
# optimal 3-roll play, its P(success) and its EV? All numbers ignore the Yahtzee
# bonus and the 63 bonus (isolated single box). Every figure is SOURCED from
# math/scene06_last_turn_numbers.py (run it to reproduce):
#   top mean count 2.1 ; count dist 0..5 = 6.49/23.63/34.40/25.04/9.12/1.33 %
#   Yahtzee 4.6% ; Full House 36.6% / EV 9.15 ; Lg Str 26.5% / 10.61
#   Sm Str 61.6% / 18.48 ; Chance 23.33 ; 4-kind 27.7% / 5.61 ; 3-kind 71.2% / 15.19
#   chance per-die 3.5 -> 4.25 -> 4.667 ; 4-kind keep-1s 52% vs keep-6s 23%
#
# 38 subscenes (a..z, za..zl). Two script beats are voiceover-only (the
# "keep 56/456" summary and the "play perfectly" concept) and get NO subscene.

# scores[0..5] Ones..Sixes | 6 3ofK | 7 4ofK | 8 FH | 9 SmS | 10 LgS |
# 11 Yahtzee | 12 Chance | 13 yahtzee-bonus.  Yahtzee = 0 so no bonus is ever
# available; top sum 62 < 63 so no top bonus either. Threes = 12 (matches the
# four-3s the demo scores, so the box reads the same before and after).
SAMPLE = [3, 6, 12, 8, 15, 18,  18, 20, 25, 30, 40, 0, 22,  0]

# scorecard row indices (asset order: Yahtzee=11, Chance=12)
R_THREES = 2
R_3KIND, R_4KIND, R_FH, R_SMS, R_LGS, R_YAH, R_CHANCE = 6, 7, 8, 9, 10, 11, 12

# ── layout ────────────────────────────────────────────────────────────────────
# Card is snapped FLUSH to the left frame edge with to_edge(LEFT) (robust to the
# card's actual width). The space that frees up on the right holds a WIDE 4th
# column; the dice + guide lines are then centered in the gutter between the
# card's real right edge and the frame's right edge (computed at runtime).
COL4_W   = 3.0                   # wide 4th column (roomy histogram)
FRAME_R  = 7.11                  # frame half-width
FRAME_T  = 4.0                   # frame half-height
DICE_DX  = 1.15                  # dice spread


class LastTurn(YahtzeeScene):
    """Scene 06 — the endgame, box by box. Subscene bodies are ANIMATION ONLY;
    each builds what it owns via a _setup_* helper, then plays."""

    def setup_scene(self):
        # Follows talking head THD — nothing on screen at frame 0.
        self.table_prob = {}   # scorecard row -> Prob-Success text  (col 4)
        self.table_ev = {}     # scorecard row -> Avg-Points text    (col 4)
        self._held = None      # (fill, border, row) of the currently-held row

    # ── shared build helpers ─────────────────────────────────────────────────
    def _setup_card(self):
        # Keep the normal 3 columns (labels/values/summary) + the new 4th info
        # column. A box is open through the whole scene, so the top bar reads as
        # "in progress" (blue), not the red "missed the 63 bonus".
        self.card = get_scorecard(
            SAMPLE, center=ORIGIN,
            fourth_column=True, fourth_width=COL4_W,
        )
        # Position by the PANEL rectangle (cells[0]) — the card's overall bounding
        # box has a phantom extension that throws off get_top()/to_edge(). Equal
        # margins: panel's left margin = its top margin.
        panel = self.card.cells[0]
        top_margin = FRAME_T - panel.get_top()[1]
        self.card.shift(RIGHT * ((-FRAME_R + top_margin) - panel.get_left()[0]))
        self.card_home = self.card.get_center().copy()
        # keep the (63) bar neutral blue the whole scene (we ignore the bonus, so
        # don't flash the red "top complete but missed 63" state at the start)
        if self.card.bar_fill is not None:
            self.card.bar_fill.set_fill(ACCENT_FILL, opacity=1.0)

    def _gutter_x(self):
        """Center x of the empty gutter between the panel's right edge and frame."""
        return (self.card.cells[0].get_right()[0] + FRAME_R) / 2

    def _setup_board(self, start=(1, 2, 3, 4, 5)):
        ax = self._gutter_x()                          # dice centered in the gutter
        half = 2 * DICE_DX + 0.7                        # lines just past the outer dice
        self.board = DiceBoard(area_x=ax, slot_dx=DICE_DX,
                               line_x=(ax - half, ax + half))
        self.board.place_initial(list(start))

    def _reset_board(self, start, run_time):
        """Send the dice back to band 0 (below the bottom line) with the given
        opening values, for a fresh 3-roll sequence in a new section."""
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=run_time)
        self.board.place_initial(list(start))
        self.play(*[FadeIn(d) for d in self.board.dice], run_time=run_time)

    def _show_dice(self, values, band, run_time):
        """Place the dice STATICALLY at `band` with `values` (fade out/in, no
        roll) — for the keep-illustration sections (full house, straights)."""
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=run_time)
        for i, d in enumerate(self.board.dice):
            d.set_value(values[i])
            d.move_to(self.board._slot_point(band, i))
            self.board.slot[i] = i
        self.board.band = band
        self.board.kept = []
        self.play(*[FadeIn(d) for d in self.board.dice], run_time=run_time)

    def _keep_up(self, idxs, run_time, hold, up_band=3):
        """The established 'keep' gesture: move the kept dice UP into the top row,
        hold, then bring them back to their row."""
        dice = [self.board.dice[i] for i in idxs]
        homes = [d.get_center().copy() for d in dice]
        self.play(*[d.animate.move_to(self.board._slot_point(up_band, s))
                    for s, d in enumerate(dice)], run_time=run_time)
        self.wait(hold)
        self.play(*[d.animate.move_to(h) for d, h in zip(dice, homes)], run_time=run_time)

    # ── the box(es) currently being covered stay highlighted for the section ───
    def _hold_row(self, rows, run_time=0.4):
        """Hold a persistent highlight on one or more rows (drops any prior hold)."""
        self._release_row(run_time=0.0)
        self._extend_hold(rows, run_time=run_time)

    def _extend_hold(self, rows, run_time=0.4):
        """Add rows to the current hold without dropping what's already held."""
        rows = [rows] if isinstance(rows, int) else list(rows)
        held = list(self._held or [])
        existing = {r for _, _, r in held}
        fades = []
        for r in rows:
            if r in existing:
                continue
            fill, border, bold = self.card._row_highlight(r, ACCENT_GOLD, 0.35)
            self.card.labels[r].save_state()
            fades += [FadeIn(fill), FadeIn(border), Transform(self.card.labels[r], bold)]
            held.append((fill, border, r))
        if fades:
            self.play(*fades, run_time=run_time)
        self._held = held

    def _release_row(self, run_time=0.3):
        held = getattr(self, "_held", None)
        if not held:
            return
        if run_time > 0:
            anims = []
            for fill, border, r in held:
                anims += [FadeOut(fill), FadeOut(border), Restore(self.card.labels[r])]
            self.play(*anims, run_time=run_time)
        else:
            for fill, border, r in held:
                self.card.labels[r].restore()
        for fill, border, r in held:
            self.remove(fill, border)
        self._held = None

    # ── column-4 bottom-block table (Prob Success | Avg Points) ───────────────
    def _col4_sub_x(self):
        cx = self.card.col4_cells[R_3KIND].get_center()[0]
        return cx - 0.52, cx + 0.52          # (prob sub-column, avg sub-column)

    def _setup_table_headers(self):
        px, ax = self._col4_sub_x()
        y = self.card.col4_cells[R_3KIND].get_top()[1] + 0.2
        prob_h = crisp_text("Success %", font_size=14, color=BLACK, font=FONT, weight="BOLD")
        avg_h = crisp_text("Avg Points", font_size=14, color=BLACK, font=FONT, weight="BOLD")
        prob_h.move_to([px, y, 0]); avg_h.move_to([ax, y, 0])
        self.col4_headers = VGroup(prob_h, avg_h)

    def _table_row(self, row, prob, ev):
        px, ax = self._col4_sub_x()
        y = self.card.col4_cells[row].get_center()[1]
        pt = crisp_text(prob, font_size=25, color=BLACK, font=FONT, weight="BOLD").move_to([px, y, 0])
        et = crisp_text(ev, font_size=25, color=BLACK, font=FONT, weight="BOLD").move_to([ax, y, 0])
        self.table_prob[row] = pt
        self.table_ev[row] = et
        return pt, et

    # ── a) intro: bring in the card, walk the boxes ──────────────────────────
    @subscene
    def intro(self):
        self._setup_card()
        in_rt, hl_rt = 1.1, 3.0

        # enter with a SHIFT (never an opacity fade — corrupts the card)
        self.card.shift(LEFT * 11)
        self.add(self.card)
        self.play(self.card.animate.move_to(self.card_home), run_time=in_rt)

        # "Highlight boxes one at a time" — a flash walking down every row.
        self.card.highlight_rows(self, list(range(13)), pulse=True,
                                 lag_ratio=0.18, run_time=hl_rt)

    # ── b) top section: roll for threes (2 -> 3 -> 4 of them) ─────────────────
    @subscene
    def top_threes(self):
        self._setup_board()
        clear_rt, in_rt, roll_rt, keep_rt, score_rt = 0.7, 0.8, 0.7, 0.5, 1.1

        # clear just the Threes box; hold it highlighted for the whole section
        self.card.transition(self, {R_THREES: None}, run_time=clear_rt)
        self._hold_row(R_THREES)
        self.play(FadeIn(self.board.lines), *[FadeIn(d) for d in self.board.dice],
                  run_time=in_rt)

        self.play(*self.board.first_roll([3, 3, 2, 4, 6]), run_time=roll_rt)   # 2 threes
        self.wait(0.2)
        self.play(*self.board.keep([0, 1]), run_time=keep_rt)
        self.play(*self.board.roll_rest([3, 5, 1]), run_time=roll_rt)          # 3 threes
        self.wait(0.2)
        self.play(*self.board.keep([0, 1, 2]), run_time=keep_rt)
        self.play(*self.board.roll_rest([3, 6]), run_time=roll_rt)             # 4 threes
        self.wait(0.3)

        self.card.upper(self, self.board.dice, 3)     # score four 3s -> 12
        self.wait(0.3)

    # ── c) histogram of "how many of the value", then park it in column 4 ─────
    @subscene
    def top_histogram(self):
        self._setup_hist()
        in_rt, move_rt = 1.0, 1.1

        # the histogram is the same for every top box, so light up the whole top
        # section (Threes is already held from b; add the other five)
        self._extend_hold([0, 1, 3, 4, 5])

        # big + readable on the right: standing bars, 0-5 labels, % on each bar
        self.play(FadeIn(self.hist, shift=UP * 0.3),
                  FadeIn(self.hist_avg1, shift=UP * 0.3), run_time=in_rt)
        self.wait(0.5)

        # park it in the TOP of column 4 (keep the % and the 0-5 labels, but drop
        # the "Number Rolled" axis label); swap the Avg for a big 2-line version
        # below the mini-histogram (live region tracks the card)
        top_c, _w, top_h = self.card.col4_region(range(6))
        mini_c = top_c + UP * top_h * 0.25
        self.hist_avg2.move_to(top_c + DOWN * top_h * 0.33)
        xlab = self.hist.x_axis_label_text
        self.hist.remove(xlab)                       # so it isn't scaled with the rest
        self.play(
            self.hist.animate.scale(0.50).move_to(mini_c),
            FadeOut(xlab),
            FadeOut(self.hist_avg1),
            FadeIn(self.hist_avg2),
            run_time=move_rt,
        )
        self._release_row()          # end the top-section highlight before the section ends
        self.wait(0.2)

    def _setup_hist(self):
        # count distribution of the target value after 3 rolls (SOURCED)
        counts = {0: 6.49, 1: 23.63, 2: 34.40, 3: 25.04, 4: 9.12, 5: 1.33}
        self.hist = get_histogram(
            None, counts=counts, is_vertical=False,      # standing bars
            center=[self._gutter_x(), -0.2, 0], width=4.4, height=2.5,
            bar_color=ACCENT_FILL, x_tick_step=1,         # label every value 0..5
            x_axis_label="Number Rolled",
            bar_labels="percent", bar_label_font_size=22,
        )
        # big single-line caption for the on-the-right display
        self.hist_avg1 = crisp_text("Avg 2.1", font_size=32, color=BLACK,
                                    font=FONT, weight="BOLD")
        self.hist_avg1.next_to(self.hist, DOWN, buff=0.3)
        # large 2-line caption for once it's parked in column 4
        self.hist_avg2 = VGroup(
            crisp_text("Avg", font_size=30, color=BLACK, font=FONT, weight="BOLD"),
            crisp_text("2.1", font_size=36, color=BLACK, font=FONT, weight="BOLD"),
        ).arrange(DOWN, buff=0.06)

    # ── d) yahtzee: keep the most-of; the example fails (33313, four 3s) ──────
    @subscene
    def yah_roll(self):
        clear_rt, reset_rt, roll_rt, keep_rt = 0.6, 0.35, 0.7, 0.5

        # open + hold the Yahtzee box (Threes already reads 12 from the demo)
        self.card.transition(self, {R_YAH: None}, run_time=clear_rt)
        self._hold_row(R_YAH)
        self._reset_board([2, 2, 4, 4, 6], reset_rt)

        self.play(*self.board.first_roll([2, 2, 4, 4, 6]), run_time=roll_rt)  # 22446
        self.wait(0.15)
        self.play(*self.board.keep([0, 1]), run_time=keep_rt)                 # keep 22
        self.play(*self.board.roll_rest([3, 3, 3]), run_time=roll_rt)         # 22333
        self.wait(0.15)
        self.play(*self.board.keep([2, 3, 4]), run_time=keep_rt)              # keep 333
        self.play(*self.board.roll_rest([3, 1]), run_time=roll_rt)            # 33313 (no yahtzee)
        self.wait(0.3)
        self.card.yahtzee(self, self.board.dice)                             # scores 0
        self.wait(0.3)

    # ── e) introduce the col-4 table; fill the Yahtzee row (5%, EV) ──────────
    @subscene
    def yah_fill(self):
        self._setup_table_headers()
        hdr_rt, fill_rt = 0.8, 0.8

        self.play(FadeIn(self.col4_headers), run_time=hdr_rt)
        pt, et = self._table_row(R_YAH, "5%", "2.3")
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()          # end the Yahtzee highlight before the section ends
        self.wait(0.2)

    # ── f) "we'll get to 3 & 4 of a kind later" — highlight those two rows ────
    @subscene
    def highlight_34kind(self):
        hl_rt, hold = 0.4, 1.3
        self.card.highlight_rows(self, [R_3KIND, R_4KIND], run_time=hl_rt, hold=hold)

    # ── g) full house: push-forward the groups you'd keep (2pair/3kind/pair/4kind)
    @subscene
    def fh_examples(self):
        clear_rt, show_rt, push_rt, morph_rt, hold = 0.5, 0.5, 0.4, 0.5, 0.7

        self.card.transition(self, {R_FH: None}, run_time=clear_rt)
        self._hold_row(R_FH)
        self._show_dice([2, 2, 4, 4, 5], band=1, run_time=show_rt)   # two pairs
        self._keep_up([0, 1, 2, 3], push_rt, hold)                 # keep 2244
        morph_dice(self, self.board.dice, [2, 2, 2, 4, 5], run_time=morph_rt)  # 3 of a kind
        self._keep_up([0, 1, 2], push_rt, hold)                    # keep 222
        morph_dice(self, self.board.dice, [2, 2, 3, 4, 5], run_time=morph_rt)  # single pair
        self._keep_up([0, 1], push_rt, hold)                       # keep 22
        morph_dice(self, self.board.dice, [2, 2, 2, 2, 5], run_time=morph_rt)  # 4 of a kind
        self._keep_up([0, 1, 2], push_rt, hold)                    # keep 3 of them

    # ── h) fill the Full House row (37%, EV 9.2) ─────────────────────────────
    @subscene
    def fh_fill(self):
        fill_rt = 0.8
        pt, et = self._table_row(R_FH, "37%", "9.2")
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()          # end the Full House highlight before the section ends
        self.wait(0.2)
