from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from manim import config as MCFG            # real frame is 16x9 (see manim.cfg)
from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice, Die
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
# Frame is 16x9 (x-radius 8.0, y-radius 4.5) — READ from MCFG, never hardcode.
# The card sits with EQUAL margins (left = top/bottom); the ~7-wide gutter to its
# right holds the dice + guide lines, centered at runtime from the card's real
# right edge (card bbox == its panel, so get_right() is accurate here).
COL4_W   = 3.0                   # wide 4th column (roomy histogram)
DICE_DX  = 1.4                   # dice spread (the gutter has room)


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
        # Normal 3 columns (labels/values/summary) + the new 4th info column.
        # (The (63) bar's colour is left to the scorecard — red when the top is
        # complete and < 63, which is correct here; we do NOT override it.)
        self.card = get_scorecard(
            SAMPLE, center=ORIGIN,
            fourth_column=True, fourth_width=COL4_W,
        )
        # Position by the panel rectangle (cells[0] == the card's bbox), against
        # the REAL frame (16x9). Equal margins: left margin = top margin.
        panel = self.card.cells[0]
        top_margin = MCFG.frame_y_radius - panel.get_top()[1]
        self.card.shift(RIGHT * ((-MCFG.frame_x_radius + top_margin) - panel.get_left()[0]))
        self.card_home = self.card.get_center().copy()

    def _gutter_x(self):
        """Center x of the gutter between the panel's right edge and the frame."""
        return (self.card.cells[0].get_right()[0] + MCFG.frame_x_radius) / 2

    def _setup_board(self, start=(1, 2, 3, 4, 5)):
        ax = self._gutter_x()                          # dice centered in the gutter
        panel_r = self.card.cells[0].get_right()[0]
        # guide lines span the gutter (clear the card + the frame edge by 0.25),
        # which keeps them centered on ax and bracketing the dice
        self.board = DiceBoard(area_x=ax, slot_dx=DICE_DX,
                               line_x=(panel_r + 0.25, MCFG.frame_x_radius - 0.25))
        self.board.place_initial(list(start))

    def _reset_board(self, start, run_time):
        """Send the dice back to band 0 (below the bottom line) with the given
        opening values, for a fresh 3-roll sequence in a new section."""
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=run_time)
        self.board.place_initial(list(start))
        self.play(*[FadeIn(d) for d in self.board.dice], run_time=run_time)

    def _show_dice(self, values, band, run_time):
        """Place the dice STATICALLY at `band` with `values` (fade out/in, no
        roll) — for the keep-illustration sections. Only fade out dice that are
        actually on screen: re-fading a die a prior section already removed makes
        manim re-add it at full opacity (a stale-value FLASH) before fading."""
        shown = [d for d in self.board.dice if d in self.mobjects]
        if shown:
            self.play(*[FadeOut(d) for d in shown], run_time=run_time)
        for i, d in enumerate(self.board.dice):
            d.set_value(values[i])
            d.move_to(self.board._slot_point(band, i))
            self.board.slot[i] = i
        self.board.band = band
        self.board.kept = []
        self.play(*[FadeIn(d) for d in self.board.dice], run_time=run_time)

    def _keep(self, keep_idxs, base_band, run_time, hold=0.0):
        """Illustrate a keep DECISION via the shared DiceBoard.show_keep convention:
        kept dice push forward one band, reroll dice go to the RIGHT — and STAY
        pushed forward (no bring-back). `base_band` encodes which reroll it is:
        1 = FIRST reroll (dice at band 1, keep -> band 2); 2 = SECOND/last roll
        (dice at band 2, keep -> band 3). See assets/dice.py for the convention."""
        self.play(*self.board.show_keep(keep_idxs, base_band), run_time=run_time)
        if hold:
            self.wait(hold)

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

    # ── column-4 bottom-block table (Prob | Avg Pts) ──────────────────────────
    def _col4_sub_x(self):
        cx = self.card.col4_cells[R_3KIND].get_center()[0]
        return cx - 0.72, cx + 0.72          # (prob sub-column, avg sub-column)

    def _setup_table_headers(self):
        px, ax = self._col4_sub_x()
        y = self.card.col4_cells[R_3KIND].get_top()[1] + 0.2
        prob_h = crisp_text("Prob", font_size=20, color=BLACK, font=FONT, weight="BOLD")
        avg_h = crisp_text("Avg Pts", font_size=20, color=BLACK, font=FONT, weight="BOLD")
        prob_h.move_to([px, y, 0]); avg_h.move_to([ax, y, 0])
        self.col4_headers = VGroup(prob_h, avg_h)

    # Heatmap colouring for the Prob / Avg Pts numbers: low = red, high = green,
    # on a FIXED conceptual scale (Prob 0-100%, Avg Pts 0-25 near the max EV).
    # Midpoint is ACCENT_ORANGE, not a pale yellow, so mid values stay readable
    # as bold text on the cream card.
    PROB_MAX, EV_MAX = 100.0, 25.0

    def _heat_color(self, alpha):
        lo, hi = ManimColor(SCORE_RED), ManimColor(SCORE_GREEN)   # hex strs -> ManimColor
        a = max(0.0, min(1.0, alpha))
        if a < 0.5:
            return interpolate_color(lo, ACCENT_ORANGE, a * 2)
        return interpolate_color(ACCENT_ORANGE, hi, (a - 0.5) * 2)

    def _val_color(self, s, denom):
        """Map a table string ('37%', '9.2') to a heatmap colour on a 0..denom
        scale; a dash (no value, e.g. Chance prob) stays neutral BLACK."""
        try:
            v = float(s.replace("%", "").strip())
        except ValueError:
            return BLACK
        return self._heat_color(v / denom)

    def _table_row(self, row, prob, ev):
        px, ax = self._col4_sub_x()
        y = self.card.col4_cells[row].get_center()[1]
        pcol, ecol = self._val_color(prob, self.PROB_MAX), self._val_color(ev, self.EV_MAX)
        pt = crisp_text(prob, font_size=29, color=pcol, font=FONT, weight="BOLD").move_to([px, y, 0])
        et = crisp_text(ev, font_size=29, color=ecol, font=FONT, weight="BOLD").move_to([ax, y, 0])
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

        # big + readable on the right (Avg 2.1 is PART of the histogram group)
        self.play(FadeIn(self.hist, shift=UP * 0.3), run_time=in_rt)
        self.wait(0.5)

        # park the WHOLE histogram — bars, %, 0-5, "Quantity Rolled" AND Avg 2.1 —
        # centered in the col-4 top block, scaled to fit its width (centered so the
        # % clear the top)
        top_c, colw, top_h = self.card.col4_region(range(6))
        self.play(self.hist.animate.scale(0.92 * colw / self.hist.width).move_to(top_c),
                  run_time=move_rt)
        self._release_row()          # end the top-section highlight before the section ends
        self.wait(0.2)

    def _setup_hist(self):
        # count distribution of the target value after 3 rolls (SOURCED)
        counts = {0: 6.49, 1: 23.63, 2: 34.40, 3: 25.04, 4: 9.12, 5: 1.33}
        self.hist = get_histogram(
            None, counts=counts, is_vertical=False,      # standing bars
            center=[self._gutter_x(), 0, 0], width=4.4, height=1.9,
            bar_color=ACCENT_FILL, x_tick_step=1,         # label every value 0..5
            x_axis_label="Quantity Rolled",
            bar_labels="percent", bar_label_font_size=22, bar_label_weight="BOLD",
            x_label_weight="BOLD", x_axis_label_weight="BOLD",
        )
        # Avg 2.1 is added INTO the histogram group so it moves + scales WITH it
        avg = crisp_text("Avg 2.1", font_size=30, color=BLACK, font=FONT, weight="BOLD")
        avg.next_to(self.hist, DOWN, buff=0.22)
        self.hist.add(avg)

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
        self._show_dice([2, 2, 4, 4, 5], band=2, run_time=show_rt)   # two pairs
        self._keep([0, 1, 2, 3], 2, push_rt, hold)                 # keep 2244
        morph_dice(self, self.board.dice, [2, 2, 2, 4, 5], run_time=morph_rt)  # 3 of a kind
        self._keep([0, 1, 2], 2, push_rt, hold)                    # keep 222
        morph_dice(self, self.board.dice, [2, 2, 3, 4, 5], run_time=morph_rt)  # single pair
        self._keep([0, 1], 2, push_rt, hold)                       # keep 22
        morph_dice(self, self.board.dice, [2, 2, 2, 2, 5], run_time=morph_rt)  # 4 of a kind
        self._keep([0, 1, 2], 2, push_rt, hold)                    # keep 3 of them

    # ── h) fill the Full House row (37%, EV 9.2) ─────────────────────────────
    @subscene
    def fh_fill(self):
        fill_rt = 0.8
        pt, et = self._table_row(R_FH, "37%", "9.2")
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()          # end the Full House highlight before the section ends
        self.wait(0.2)

    # ── the two large straights, 2/3/4/5 aligned in columns (12345 / 23456) ───
    def _setup_lgs_pair(self):
        ax = self._gutter_x()
        sp, sz, dy = 1.05, 0.8, 0.95
        def die(v, col, y):
            return Die(value=v, size=sz).move_to([ax + (col - 2.5) * sp, y, 0])
        self.lgs_top = VGroup(*[die(v, c, dy) for c, v in enumerate([1, 2, 3, 4, 5])])
        self.lgs_bot = VGroup(*[die(v, c + 1, -dy) for c, v in enumerate([2, 3, 4, 5, 6])])

    # ── i) large straight: the two ways to make one ──────────────────────────
    @subscene
    def lgs_intro(self):
        clear_rt, out_rt, in_rt = 0.5, 0.4, 0.8
        self.card.transition(self, {R_FH: 25, R_LGS: None}, run_time=clear_rt)  # refill FH, open LgS
        self._hold_row(R_LGS)
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=out_rt)      # clear the FH dice
        self._setup_lgs_pair()
        self.play(FadeIn(self.lgs_top, shift=UP * 0.2),
                  FadeIn(self.lgs_bot, shift=DOWN * 0.2), run_time=in_rt)

    # ── j) you need 2,3,4,5 and either a 1 or 6 ───────────────────────────────
    @subscene
    def lgs_strategy(self):
        hl = 1.2
        mid = [*self.lgs_top[1:5], *self.lgs_bot[0:4]]     # the 2,3,4,5 in both rows
        ends = [self.lgs_top[0], self.lgs_bot[4]]          # the lone 1 and 6
        highlight(self, mid, hold=hl)
        highlight(self, ends, hold=hl)

    # ── k) roll a 2/3/4/5 -> keep one of each (22334 -> keep 234) ─────────────
    @subscene
    def lgs_keep2345(self):
        out_rt, show_rt, push_rt, hold = 0.4, 0.5, 0.4, 0.9
        self.play(FadeOut(self.lgs_top), FadeOut(self.lgs_bot), run_time=out_rt)
        self.lgs_top = self.lgs_bot = None
        self._show_dice([2, 2, 3, 3, 4], band=2, run_time=show_rt)   # 22334
        self._keep([0, 2, 4], 2, push_rt, hold)                     # keep one 2, 3, 4

    # ── l) 1/6 keeps a spot only if you'd keep >=4 dice (12346 -> keep 1234) ──
    @subscene
    def lgs_1or6(self):
        morph_rt, push_rt, hold = 0.5, 0.4, 0.9
        morph_dice(self, self.board.dice, [1, 2, 3, 4, 6], run_time=morph_rt)   # 12346
        self._keep([0, 1, 2, 3], 2, push_rt, hold)                  # keep the 1 (>=4 dice)

    # ── m) otherwise reroll the 1s/6s (12336 -> keep 23) ─────────────────────
    @subscene
    def lgs_reroll16(self):
        morph_rt, push_rt, hold = 0.5, 0.4, 0.9
        morph_dice(self, self.board.dice, [1, 2, 3, 3, 6], run_time=morph_rt)   # 12336
        self._keep([1, 2], 2, push_rt, hold)                        # drop the 1 & 6, keep 23

    # ── n) fill the Large Straight row (27%, EV 10.6) ────────────────────────
    @subscene
    def lgs_fill(self):
        fill_rt = 0.8
        pt, et = self._table_row(R_LGS, "27%", "10.6")
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()
        self.wait(0.2)

    # ── the three small straights (1234/2345/3456), 3/4 aligned, + a greyed
    #    "extra die" column after the 6 ────────────────────────────────────────
    def _setup_sms_triple(self):
        ax = self._gutter_x()
        sp, sz, dy = 0.92, 0.7, 1.05
        def die(v, col, y):
            return Die(value=v, size=sz).move_to([ax + (col - 3) * sp, y, 0])
        ys = [dy, 0.0, -dy]
        straights = [[1, 2, 3, 4], [2, 3, 4, 5], [3, 4, 5, 6]]
        starts = [0, 1, 2]                       # each row's first value-column
        self.sms_rows = VGroup(); self.sms_34 = VGroup(); self.sms_other = VGroup()
        for vals, c0, y in zip(straights, starts, ys):
            for j, v in enumerate(vals):
                d = die(v, c0 + j, y)
                self.sms_rows.add(d)
                (self.sms_34 if v in (3, 4) else self.sms_other).add(d)
        # unused 5th die: 1/2/3 so no row reads as a large straight (e.g. 2345+1)
        self.sms_grey = VGroup(*[die(gv, 6, y).set_opacity(0.3)
                                 for gv, y in zip([1, 2, 3], ys)])

    # ── o) small straight: three ways + the extra unused die ─────────────────
    @subscene
    def sms_intro(self):
        clear_rt, out_rt, in_rt = 0.5, 0.4, 0.8
        self.card.transition(self, {R_LGS: 40, R_SMS: None}, run_time=clear_rt)  # refill LgS, open SmS
        self._hold_row(R_SMS)
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=out_rt)
        self._setup_sms_triple()
        self.play(FadeIn(self.sms_rows), FadeIn(self.sms_grey), run_time=in_rt)

    # ── p) always need a 3 and a 4 ───────────────────────────────────────────
    @subscene
    def sms_need34(self):
        hl = 1.2
        highlight(self, [*self.sms_34], hold=hl)
        highlight(self, [*self.sms_other], hold=hl)

    # ── q) no 3 or 4 -> reroll everything (12256) ────────────────────────────
    @subscene
    def sms_no34(self):
        out_rt, show_rt, hold = 0.4, 0.5, 1.1
        self.play(FadeOut(self.sms_rows), FadeOut(self.sms_grey), run_time=out_rt)
        self.sms_rows = self.sms_34 = self.sms_other = self.sms_grey = None
        self._show_dice([1, 2, 2, 5, 6], band=2, run_time=show_rt)   # no 3 or 4
        self.wait(hold)                                              # keep nothing, reroll all

    # ── r) keep one each of 3,4 (and 2,5) — 22336 -> keep 23 ─────────────────
    @subscene
    def sms_keep(self):
        morph_rt, push_rt, hold = 0.5, 0.4, 0.9
        morph_dice(self, self.board.dice, [2, 2, 3, 3, 6], run_time=morph_rt)   # 22336
        self._keep([0, 2], 2, push_rt, hold)                        # keep 2, 3

    # ── s) keep a 1 (1&2 no 5) / a 6 (5&6 no 2): 12236->123, 13356->356 ──────
    @subscene
    def sms_1or6(self):
        morph_rt, push_rt, hold = 0.5, 0.4, 0.8
        morph_dice(self, self.board.dice, [1, 2, 2, 3, 6], run_time=morph_rt)   # 12236
        self._keep([0, 1, 3], 2, push_rt, hold)                     # keep 1, 2, 3
        morph_dice(self, self.board.dice, [1, 3, 3, 5, 6], run_time=morph_rt)   # 13356
        self._keep([1, 3, 4], 2, push_rt, hold)                     # keep 3, 5, 6

    # ── t) fill the Small Straight row (62%, EV 18.5) ────────────────────────
    @subscene
    def sms_fill(self):
        fill_rt = 0.8
        pt, et = self._table_row(R_SMS, "62%", "18.5")
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()
        self.wait(0.2)

    # ── CHANCE (u-za) — vertical column of dice 6..1 on the LEFT; arrows point
    #   RIGHT to a second column: kept dice map to their own dupe dice, rerolled
    #   dice map to the reroll-value NUMBER (3.5 -> 4.25). Result avg walks
    #   3.5(one die) -> 4.25(2nd reroll) -> 4.67(1st reroll).
    def _setup_chance_col(self):
        ax = self._gutter_x()
        self.ch_x = ax - 2.1                       # main column (left)
        self.ch_x2 = ax + 1.5                      # second column of targets (right)
        self.ch_sz, gap, y0 = 0.7, 0.82, 1.95      # bigger dice; gap > size (no overlap)
        self.ch_dice = VGroup(*[
            Die(value=v, size=self.ch_sz).move_to([self.ch_x, y0 - i * gap, 0])
            for i, v in enumerate([6, 5, 4, 3, 2, 1])])     # [0]=6 (top) .. [5]=1 (bottom)
        self.ch_ybot = -3.0                        # bottom summary labels (extra room below the 1)
        self.ch_title = crisp_text("Second Reroll", font_size=26, color=BLACK, font=FONT,
                                   weight="BOLD").move_to([(self.ch_x + self.ch_x2) / 2, 2.75, 0])
        self.ch_avg = crisp_text("Avg 3.5", font_size=28, color=BLACK, font=FONT,
                                 weight="BOLD").move_to([self.ch_x, self.ch_ybot, 0])  # single-die avg

    def _ch_arrows(self, keep_n, reroll_val):
        """Keep-arrows (kept die -> its own dupe die) and reroll-arrows (each
        rerolled die -> its OWN copy of the reroll number), each labelled above.
        Every arrow shares the SAME start x (die right edge) and SAME end x
        (tgt_x = the second column's left edge), so all arrows are identical
        length and built identically; the dupe dice and the reroll numbers are
        both LEFT-aligned to tgt_x, so the two second-column stacks line up.
        Returns (keeps, rerolls), each a list of (arrow, mob, label) triples."""
        keep, reroll = self.ch_dice[:keep_n], self.ch_dice[keep_n:]
        tgt_x = self.ch_x2 - self.ch_sz / 2         # shared left edge of column 2
        keeps = []
        for d in keep:
            y = d.get_center()[1]
            dup = Die(value=d.value, size=self.ch_sz).move_to([self.ch_x2, y, 0])
            a = Arrow(d.get_right(), [tgt_x, y, 0], buff=0.1, color=SCORE_GREEN,
                      stroke_width=5, max_tip_length_to_length_ratio=0.28)
            lbl = crisp_text("keep", font_size=17, color=SCORE_GREEN, font=FONT,
                             weight="BOLD").next_to(a, UP, buff=0.0)
            keeps.append((a, dup, lbl))
        rerolls = []
        for d in reroll:
            y = d.get_center()[1]
            num = crisp_text(reroll_val, font_size=26, color=BLACK, font=FONT,
                             weight="BOLD").move_to([self.ch_x2, y, 0])   # centered below the dupe dice
            a = Arrow(d.get_right(), [tgt_x, y, 0], buff=0.1, color=SCORE_RED,
                      stroke_width=5, max_tip_length_to_length_ratio=0.28)
            lbl = crisp_text("reroll", font_size=17, color=SCORE_RED, font=FONT,
                             weight="BOLD").next_to(a, UP, buff=0.0)
            rerolls.append((a, num, lbl))
        return keeps, rerolls

    # ── u) chance: treat each die on its own ─────────────────────────────────
    @subscene
    def chance_intro(self):
        clear_rt, out_rt = 0.5, 0.4
        self.card.transition(self, {R_SMS: 30, R_CHANCE: None}, run_time=clear_rt)
        self._hold_row(R_CHANCE)
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=out_rt)

    # ── v) second reroll: the column of dice, one die averages 3.5 ───────────
    @subscene
    def chance_col(self):
        in_rt = 0.8
        self._setup_chance_col()
        self.play(FadeIn(self.ch_title), FadeIn(self.ch_dice), FadeIn(self.ch_avg), run_time=in_rt)

    # ── w) keep 4/5/6 -> themselves; reroll 1/2/3 -> its own 3.5 ─────────────
    @subscene
    def chance_2nd_arrows(self):
        reroll_rt, keep_rt = 0.8, 0.8
        keeps, rerolls = self._ch_arrows(keep_n=3, reroll_val="3.5")
        self.ch_2nd = VGroup(*[m for tr in keeps for m in tr],
                             *[m for tr in rerolls for m in tr])
        self.play(*[GrowArrow(a) for a, _, _ in rerolls],      # reroll first
                  *[FadeIn(n) for _, n, _ in rerolls], *[FadeIn(l) for _, _, l in rerolls],
                  run_time=reroll_rt)
        self.play(*[GrowArrow(a) for a, _, _ in keeps],        # then keep
                  *[FadeIn(dup) for _, dup, _ in keeps], *[FadeIn(l) for _, _, l in keeps],
                  run_time=keep_rt)

    # ── x) that strategy averages 4.25 (end of the SECOND column) ────────────
    @subscene
    def chance_425(self):
        rt = 0.6
        self.ch_result = crisp_text("Avg 4.25", font_size=28, color=BLACK, font=FONT,
                                    weight="BOLD").move_to([self.ch_x2, self.ch_avg.get_center()[1], 0])
        self.play(FadeIn(self.ch_result, shift=UP * 0.15), run_time=rt)

    # ── y) first reroll: rerolling now yields 4.25, so reroll the 4 too. The 1
    #      arrow is drawn first. ──────────────────────────────────────────────
    @subscene
    def chance_1st(self):
        title_rt, arr_rt = 0.7, 0.5
        new_title = crisp_text("First Reroll", font_size=26, color=BLACK, font=FONT,
                               weight="BOLD").move_to(self.ch_title.get_center())
        self.play(Transform(self.ch_title, new_title),
                  FadeOut(self.ch_2nd), FadeOut(self.ch_result), run_time=title_rt)
        keeps, rerolls = self._ch_arrows(keep_n=2, reroll_val="4.25")  # keep 5,6; reroll 1-4
        self.ch_1st = VGroup(*[m for tr in keeps for m in tr],
                             *[m for tr in rerolls for m in tr])
        a1, n1, l1 = rerolls[-1]                    # bottom die = the 1
        self.play(GrowArrow(a1), FadeIn(n1), FadeIn(l1), run_time=arr_rt)
        self._ch_1st_rest = (keeps, rerolls[:-1])

    # ── z) keep 5/6, reroll 1-4 (the rest of the arrows) ─────────────────────
    @subscene
    def chance_rest_arrows(self):
        reroll_rt, keep_rt = 0.8, 0.8
        keeps, rest = self._ch_1st_rest             # rest = reroll triples except the 1
        self.play(*[GrowArrow(a) for a, _, _ in rest],      # reroll first
                  *[FadeIn(n) for _, n, _ in rest], *[FadeIn(l) for _, _, l in rest],
                  run_time=reroll_rt)
        self.play(*[GrowArrow(a) for a, _, _ in keeps],     # then keep
                  *[FadeIn(dup) for _, dup, _ in keeps], *[FadeIn(l) for _, _, l in keeps],
                  run_time=keep_rt)

    # ── za) 4 2/3 per die -> 23.3 total for chance ───────────────────────────
    @subscene
    def chance_fill(self):
        avg_rt, fill_rt = 0.6, 0.8
        self.ch_result = crisp_text("Avg 4.67", font_size=28, color=BLACK, font=FONT,
                                    weight="BOLD").move_to([self.ch_x2, self.ch_avg.get_center()[1], 0])
        self.play(FadeIn(self.ch_result, shift=UP * 0.15), run_time=avg_rt)
        pt, et = self._table_row(R_CHANCE, "–", "23.3")   # prob = dash, EV = 23.3
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()
        self.wait(0.2)

    # ── zb) the complicated cases: 3 & 4 of a kind ───────────────────────────
    @subscene
    def fourk_highlight(self):
        out_rt, clear_rt, hl_rt, hold = 0.4, 0.5, 0.4, 1.3
        # clear the chance illustration, refill Chance, open 4-of-a-kind
        self.play(FadeOut(self.ch_dice), FadeOut(self.ch_title), FadeOut(self.ch_avg),
                  FadeOut(self.ch_1st), FadeOut(self.ch_result), run_time=out_rt)
        self.ch_dice = self.ch_title = self.ch_avg = self.ch_1st = self.ch_result = None
        self.card.transition(self, {R_CHANCE: 22, R_4KIND: None}, run_time=clear_rt)
        self.card.highlight_rows(self, [R_3KIND, R_4KIND], run_time=hl_rt, hold=hold)
        self._hold_row(R_4KIND)

    # ── zc) last roll: keep whatever you have most of (11156 -> 111) ──────────
    @subscene
    def fourk_11156(self):
        show_rt, push_rt, hold = 0.5, 0.4, 0.9
        self._show_dice([1, 1, 1, 5, 6], band=2, run_time=show_rt)   # LAST roll -> band 2
        self._keep([0, 1, 2], 2, push_rt, hold)                     # keep 111

    # ── zd) already have 4oak -> reroll the last die if <=3 (44442 -> 4444) ──
    @subscene
    def fourk_44442(self):
        morph_rt, push_rt, hold = 0.5, 0.4, 0.9
        morph_dice(self, self.board.dice, [4, 4, 4, 4, 2], run_time=morph_rt)   # still last roll
        self._keep([0, 1, 2, 3], 2, push_rt, hold)                  # keep 4444, reroll the 2

    # ── ze) FIRST roll: keep 4oak, reroll the other die if <5 (33334 -> 3333) ─
    @subscene
    def fourk_33334(self):
        show_rt, push_rt, hold = 0.5, 0.4, 0.9
        self._show_dice([3, 3, 3, 3, 4], band=1, run_time=show_rt)   # FIRST reroll -> band 1 (lower)
        self._keep([0, 1, 2, 3], 1, push_rt, hold)                  # keep 3333, reroll the 4

    # ── the two "success bars" for 11166: keep the 1s vs keep the 6s ─────────
    def _fk_bar(self, dval, w, txt, y, color):
        ax = self._gutter_x()
        x0 = ax - 3.0
        d = Die(value=dval, size=0.55).move_to([x0, y, 0])
        bar = Rectangle(width=max(w, 0.04), height=0.42, fill_color=color,
                        fill_opacity=1.0, stroke_width=1.5, stroke_color=BLACK)
        bar.move_to([x0 + 0.65 + w / 2, y, 0])
        lbl = crisp_text(txt, font_size=24, color=BLACK, font=FONT,
                         weight="BOLD").next_to(bar, RIGHT, buff=0.15)
        return VGroup(d, bar, lbl), bar, lbl

    # ── zf) 3 ones vs 2 sixes: keeping the 1s wins on SUCCESS (52% vs 23%) ────
    @subscene
    def fourk_11166_bars(self):
        show_rt, bar_rt = 0.5, 0.8
        self._show_dice([1, 1, 1, 6, 6], band=1, run_time=show_rt)   # FIRST reroll -> band 1
        # bars centered between the top & middle guide lines (band 2, ~1.125)
        g1, self.fk_bar1, self.fk_lbl1 = self._fk_bar(1, 0.52 * 4.0, "52%", 1.575, SCORE_GREEN)
        g6, self.fk_bar6, self.fk_lbl6 = self._fk_bar(6, 0.23 * 4.0, "23%", 0.675, SCORE_GREEN)
        self.fk_bars = VGroup(g1, g6)
        self.play(FadeIn(g1), FadeIn(g6), run_time=bar_rt)

    # ── zg) bars now = POINTS-IF-SUCCEED (full width), with the SUCCESS % filled,
    #      so the FILLED AREA = EV. Keeping the 6s wins on points (6.2 vs 4.2). ──
    #      SOURCED (math/scene06_last_turn_numbers.py): pts-if-succeed 8.1 / 27.1;
    #      success 52% / 23%; filled = EV = 4.2 / 6.2.
    @subscene
    def fourk_ev_bars(self):
        rt = 0.9
        ax = self._gutter_x(); x0 = ax - 3.0
        sc = 0.15
        def evbar(dval, y, pts, frac, ev):
            d = Die(value=dval, size=0.55).move_to([x0, y, 0])
            fw = pts * sc
            outline = Rectangle(width=fw, height=0.5, fill_opacity=0.0,
                                stroke_color=BLACK, stroke_width=2).move_to([x0 + 0.65 + fw / 2, y, 0])
            fill = Rectangle(width=max(fw * frac, 0.03), height=0.5, fill_color=ACCENT_FILL,
                             fill_opacity=1.0, stroke_width=0)
            fill.align_to(outline, LEFT).set_y(y)
            lbl = crisp_text(f"avg {ev}", font_size=22, color=BLACK, font=FONT,
                             weight="BOLD").next_to(outline, RIGHT, buff=0.15)
            return VGroup(d, fill, outline, lbl)
        new = VGroup(evbar(1, 1.575, 8.1, 0.52, "4.2"), evbar(6, 0.675, 27.1, 0.23, "6.2"))
        self.play(FadeOut(self.fk_bars), FadeIn(new), run_time=rt)
        self.fk_bars = new

    # ── zh) several cases where fewer-larger beats more-smaller (keeps SOURCED)
    @subscene
    def fourk_examples(self):
        out_rt, show_rt, morph_rt, push_rt, hold = 0.4, 0.5, 0.5, 0.35, 0.7
        self.play(FadeOut(self.fk_bars), run_time=out_rt)
        self.fk_bars = None
        cases = [([1, 1, 1, 4, 4], [3, 4]), ([1, 1, 1, 5, 5], [3, 4]),   # keep 44 / 55
                 ([2, 2, 3, 5, 6], [4]),    ([1, 1, 2, 3, 6], [4]),      # keep the 6
                 ([1, 1, 2, 3, 5], [4]),    ([1, 1, 2, 3, 4], [4])]      # keep the 5 / 4
        # FIRST reroll -> band 1; each case enters already pushed forward and
        # morphs to the next (no push-and-back)
        self._show_dice(cases[0][0], band=1, run_time=show_rt)
        self._keep(cases[0][1], 1, push_rt, hold)
        for vals, keep in cases[1:]:
            morph_dice(self, self.board.dice, vals, run_time=morph_rt)
            self._keep(keep, 1, push_rt, hold)

    # ── zi) fill the 4-of-a-kind row (28%, EV 5.6) ───────────────────────────
    @subscene
    def fourk_fill(self):
        fill_rt = 0.8
        pt, et = self._table_row(R_4KIND, "28%", "5.6")
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()
        self.wait(0.2)

    # ── zj) 3 of a kind, second reroll: keep most; if 3oak reroll other 2 (<4)
    @subscene
    def threek_2nd(self):
        clear_rt, show_rt, morph_rt, push_rt, hold = 0.5, 0.5, 0.5, 0.4, 0.9
        self.card.transition(self, {R_4KIND: 20, R_3KIND: None}, run_time=clear_rt)  # refill 4K, open 3K
        self._hold_row(R_3KIND)
        self._show_dice([2, 2, 3, 4, 5], band=2, run_time=show_rt)   # 22345, 2nd reroll -> band 2
        self._keep([0, 1], 2, push_rt, hold)                        # keep 22
        morph_dice(self, self.board.dice, [3, 3, 3, 3, 1], run_time=morph_rt)   # 33331
        self._keep([0, 1, 2], 2, push_rt, hold)                     # keep 333 (reroll extra 3 & the 1)

    # ── zk) first roll: usually keep the most, but many exceptions — fewer of a
    #      LARGER number over more of a smaller one (all SOURCED, 3-kind stage A) ─
    @subscene
    def threek_1st(self):
        show_rt, morph_rt, push_rt, hold = 0.5, 0.5, 0.4, 0.9
        # 3-kind-SPECIFIC counterintuitive keeps (the 4-kind answer differs here):
        # A RANGE of 3-kind-SPECIFIC keeps (the 4-kind answer differs), varying
        # both the DROPPED value (2s, 1s) and the KEPT shape (single/pair/pair+):
        cases = [([2, 2, 3, 4, 5], [4]),       # 22345: keep the single 5 over the pair of 2s (4K keeps 22)
                 ([1, 1, 1, 3, 3], [3, 4]),    # 11133: keep the pair of 3s over THREE 1s (4K keeps 111)
                 ([2, 2, 3, 3, 6], [2, 3, 4])] # 22336: keep 3,3,6 over the pair of 2s (4K keeps 33)
        self._show_dice(cases[0][0], band=1, run_time=show_rt)   # FIRST reroll -> band 1
        self._keep(cases[0][1], 1, push_rt, hold)
        for vals, keep in cases[1:]:
            morph_dice(self, self.board.dice, vals, run_time=morph_rt)
            self._keep(keep, 1, push_rt, hold)

    # ── zl) fill the 3-of-a-kind row (71%, EV 15) ────────────────────────────
    @subscene
    def threek_fill(self):
        fill_rt = 0.8
        pt, et = self._table_row(R_3KIND, "71%", "15.0")
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()
        self.wait(0.5)
