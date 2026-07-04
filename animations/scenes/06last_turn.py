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

    def _table_row(self, row, prob, ev):
        px, ax = self._col4_sub_x()
        y = self.card.col4_cells[row].get_center()[1]
        pt = crisp_text(prob, font_size=29, color=BLACK, font=FONT, weight="BOLD").move_to([px, y, 0])
        et = crisp_text(ev, font_size=29, color=BLACK, font=FONT, weight="BOLD").move_to([ax, y, 0])
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
        # the "Number Rolled" axis label); scale it to ~90% of the column width,
        # sit it a bit low so the % labels clear the top, Avg 2.1 on one line below
        top_c, colw, top_h = self.card.col4_region(range(6))
        scale = 0.9 * colw / self.hist.width
        mini_c = top_c + UP * top_h * 0.12
        self.hist_avg2.move_to(top_c + DOWN * top_h * 0.36)
        xlab = self.hist.x_axis_label_text
        self.hist.remove(xlab)                       # so it isn't scaled with the rest
        self.play(
            self.hist.animate.scale(scale).move_to(mini_c),
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
            center=[self._gutter_x(), -0.2, 0], width=4.4, height=2.2,
            bar_color=ACCENT_FILL, x_tick_step=1,         # label every value 0..5
            x_axis_label="Number Rolled",
            bar_labels="percent", bar_label_font_size=22, bar_label_weight="BOLD",
        )
        # big single-line caption for the on-the-right display
        self.hist_avg1 = crisp_text("Avg 2.1", font_size=32, color=BLACK,
                                    font=FONT, weight="BOLD")
        self.hist_avg1.next_to(self.hist, DOWN, buff=0.3)
        # single-line caption (uniform size) for once it's parked in column 4
        self.hist_avg2 = crisp_text("Avg 2.1", font_size=30, color=BLACK,
                                    font=FONT, weight="BOLD")

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
        self._show_dice([2, 2, 4, 4, 5], band=2, run_time=show_rt)   # two pairs (one row below top)
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
        self._keep_up([0, 2, 4], push_rt, hold)                     # keep one 2, 3, 4

    # ── l) 1/6 keeps a spot only if you'd keep >=4 dice (12346 -> keep 1234) ──
    @subscene
    def lgs_1or6(self):
        morph_rt, push_rt, hold = 0.5, 0.4, 0.9
        morph_dice(self, self.board.dice, [1, 2, 3, 4, 6], run_time=morph_rt)   # 12346
        self._keep_up([0, 1, 2, 3], push_rt, hold)                  # keep the 1 (>=4 dice)

    # ── m) otherwise reroll the 1s/6s (12336 -> keep 23) ─────────────────────
    @subscene
    def lgs_reroll16(self):
        morph_rt, push_rt, hold = 0.5, 0.4, 0.9
        morph_dice(self, self.board.dice, [1, 2, 3, 3, 6], run_time=morph_rt)   # 12336
        self._keep_up([1, 2], push_rt, hold)                        # drop the 1 & 6, keep 23

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
        self.sms_grey = VGroup(*[die(1, 6, y).set_opacity(0.3) for y in ys])  # unused 5th die

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
        self._keep_up([0, 2], push_rt, hold)                        # keep 2, 3

    # ── s) keep a 1 (1&2 no 5) / a 6 (5&6 no 2): 12236->123, 13356->356 ──────
    @subscene
    def sms_1or6(self):
        morph_rt, push_rt, hold = 0.5, 0.4, 0.8
        morph_dice(self, self.board.dice, [1, 2, 2, 3, 6], run_time=morph_rt)   # 12236
        self._keep_up([0, 1, 3], push_rt, hold)                     # keep 1, 2, 3
        morph_dice(self, self.board.dice, [1, 3, 3, 5, 6], run_time=morph_rt)   # 13356
        self._keep_up([1, 3, 4], push_rt, hold)                     # keep 3, 5, 6

    # ── t) fill the Small Straight row (62%, EV 18.5) ────────────────────────
    @subscene
    def sms_fill(self):
        fill_rt = 0.8
        pt, et = self._table_row(R_SMS, "62%", "18.5")
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()
        self.wait(0.2)

    # ── CHANCE (u-aa) — ROUGH first pass; arrow choreography needs feel-tuning ─
    #   a vertical column of dice 6..1; keep the high ones (>3.5), reroll the low
    #   ones. Numbers walk 3.5 -> 4.25 (2nd reroll) -> 4.67 (1st reroll).
    def _setup_chance_col(self):
        ax = self._gutter_x()
        self.ch_x = ax - 1.7                       # column on the left; arrows go right
        sz, gap, y0 = 0.6, 0.52, 1.35
        self.ch_dice = VGroup(*[
            Die(value=v, size=sz).move_to([self.ch_x, y0 - i * gap, 0])
            for i, v in enumerate([6, 5, 4, 3, 2, 1])])     # [0]=6 (top) .. [5]=1 (bottom)
        self.ch_title = crisp_text("Second Reroll", font_size=26, color=BLACK,
                                   font=FONT, weight="BOLD").move_to([self.ch_x, 2.15, 0])
        self.ch_avg = crisp_text("Avg 3.5", font_size=30, color=BLACK,
                                 font=FONT, weight="BOLD").move_to([self.ch_x, -1.65, 0])

    def _keep_arrow(self, d):
        return Arrow([d.get_right()[0], d.get_center()[1], 0],
                     [self.ch_x + 1.5, d.get_center()[1], 0],
                     buff=0.1, color=SCORE_GREEN, stroke_width=5)

    def _reroll_arrow(self, d):
        return Arrow(d.get_right(), self.ch_avg.get_top() + UP * 0.05,
                     buff=0.12, color=SCORE_RED, stroke_width=5,
                     max_tip_length_to_length_ratio=0.2)

    # ── u) chance: treat each die on its own ─────────────────────────────────
    @subscene
    def chance_intro(self):
        clear_rt, out_rt = 0.5, 0.4
        self.card.transition(self, {R_SMS: 30, R_CHANCE: None}, run_time=clear_rt)
        self._hold_row(R_CHANCE)
        self.play(*[FadeOut(d) for d in self.board.dice], run_time=out_rt)

    # ── v) second reroll: one die averages 3.5 ───────────────────────────────
    @subscene
    def chance_col(self):
        in_rt = 0.8
        self._setup_chance_col()
        self.play(FadeIn(self.ch_title), FadeIn(self.ch_dice), FadeIn(self.ch_avg),
                  run_time=in_rt)

    # ── w) keep 4/5/6 (above 3.5), reroll 1/2/3 (below) ──────────────────────
    @subscene
    def chance_2nd_arrows(self):
        rt = 0.8
        ke = VGroup(*[self._keep_arrow(d) for d in self.ch_dice[0:3]])       # 6,5,4
        rr = VGroup(*[self._reroll_arrow(d) for d in self.ch_dice[3:6]])     # 3,2,1
        kl = crisp_text("keep", font_size=24, color=SCORE_GREEN, font=FONT,
                        weight="BOLD").move_to([self.ch_x + 2.0, self.ch_dice[1].get_center()[1], 0])
        rl = crisp_text("reroll", font_size=24, color=SCORE_RED, font=FONT,
                        weight="BOLD").move_to([self.ch_x + 1.15, self.ch_dice[4].get_center()[1], 0])
        self.ch_arrows = VGroup(ke, rr, kl, rl)
        self.play(*[GrowArrow(a) for a in ke], *[GrowArrow(a) for a in rr],
                  FadeIn(kl), FadeIn(rl), run_time=rt)

    # ── x) that strategy averages 4.25 ───────────────────────────────────────
    @subscene
    def chance_425(self):
        rt = 0.6
        new = crisp_text("Avg 4.25", font_size=30, color=BLACK, font=FONT,
                         weight="BOLD").move_to(self.ch_avg.get_center())
        self.play(Transform(self.ch_avg, new), run_time=rt)

    # ── y) first reroll now uses 4.25 (2 chances left), so reroll the 4 too ──
    @subscene
    def chance_1st(self):
        title_rt, arr_rt = 0.7, 0.5
        new_title = crisp_text("First Reroll", font_size=26, color=BLACK, font=FONT,
                               weight="BOLD").move_to(self.ch_title.get_center())
        self.play(Transform(self.ch_title, new_title), FadeOut(self.ch_arrows),
                  run_time=title_rt)
        a1 = self._reroll_arrow(self.ch_dice[5])          # the 1 -> reroll (4.25)
        self.ch_first = VGroup(a1)
        self.play(GrowArrow(a1), run_time=arr_rt)

    # ── z) keep 5/6, reroll 1-4 ──────────────────────────────────────────────
    @subscene
    def chance_rest_arrows(self):
        rt = 0.8
        ke = VGroup(*[self._keep_arrow(d) for d in self.ch_dice[0:2]])       # 6,5
        rr = VGroup(*[self._reroll_arrow(d) for d in self.ch_dice[2:5]])     # 4,3,2 (1 already drawn)
        self.ch_first.add(ke, rr)
        self.play(*[GrowArrow(a) for a in ke], *[GrowArrow(a) for a in rr], run_time=rt)

    # ── aa) 4 2/3 per die -> 23 1/3 total for chance ─────────────────────────
    @subscene
    def chance_fill(self):
        avg_rt, fill_rt = 0.6, 0.8
        new = crisp_text("Avg 4.67", font_size=30, color=BLACK, font=FONT,
                         weight="BOLD").move_to(self.ch_avg.get_center())
        self.play(Transform(self.ch_avg, new), run_time=avg_rt)
        pt, et = self._table_row(R_CHANCE, "–", "23⅓")   # prob = dash, EV = 23 1/3
        self.play(FadeIn(pt, shift=UP * 0.15), FadeIn(et, shift=UP * 0.15), run_time=fill_rt)
        self._release_row()
        self.wait(0.2)
