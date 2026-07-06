from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from bpkfigures.style import ACCENT_GOLD, ACCENT_FILL, ACCENT_RED
from bpkfigures.card import get_card
from assets.scorecard import get_scorecard


# ══ numbers (all SOURCED — see math/scene12_numbers.py) ═══════════════════════
#   start        = V(empty)                 = 254.6
#   after 3 box  = 12 + V(Threes=12)        = 257.4  (four 3s — a GOOD turn)
#   after 4 kind = 12 + V(4Kind=12)         = 247.5  (pretty bad)
#   after 6 box  = 12 + V(Sixes=12, two 6s) = 232.2  (really bad)
EV_START = 254.6
EV_STEPS = [(2, 257.4), (7, 247.5), (5, 232.2)]   # (scorecard row, expected total)

# ── example scorecards (row order = SCORE_ROWS; 13 = yahtzee bonus) ────────────
#   0-5 Ones..Sixes | 6 3ofK | 7 4ofK | 8 FH | 9 SmS | 10 LgS | 11 Yz | 12 Ch | 13 yb
# Beat c: A wins by 1 bonus pt AND on total (263/8 vs 252/7); each is missing a
# bonus the other has (A: no LgS; B: no 4ofK, no Yz), yet the LOSER (B) leads in
# raw top section, 3-kind and chance.
CARD_A = [3, 6, 9, 12, 15, 18, 18, 22, 25, 30,  0, 50, 20, 0]
CARD_B = [3, 8, 12, 12, 15, 18, 26,  0, 25, 30, 40,  0, 28, 0]
# Beat d: full except Fours(3)/Sixes(5)/SmS(9)/Yahtzee(11); top devs sum to +5.
CARD_D = [1, 8, 9, None, 20, None, 20, 18, 25, None, 40, None, 22, 0]
D_TOP_DEVS = {0: -2, 1: +2, 2: 0, 4: +5}      # filled top box -> (score − 3×face)
# Beat e: two mid-game 4-col cards; LEFT clearly ahead (229/7 vs 148/5). RIGHT
# keeps enough top open that zeroing the 1s does NOT immediately kill the bonus.
CARD_L = [3, 6, 9, 12, 15, 18, 22, 24, 25, None, 40, None, 20, 0]           # open: SmS, Yz
CARD_R = [None, 8, 12, None, None, None, 18, None, 25, 30, 40, None, 15, 0]  # open: Ones,Fours,Fives,Sixes,4ofK,Yz

# ── scorecard row indices (asset convention) ──────────────────────────────────
R_3K, R_4K, R_FH, R_SS, R_LS, R_YZ, R_CH = 6, 7, 8, 9, 10, 11, 12
TOP_ROWS = list(range(6))

# ── layout ────────────────────────────────────────────────────────────────────
CARD_L_POS = LEFT_SC                      # beat a/b card (matches scene 07 layout)
GAP        = 0.45
NUM_POS    = [3.1, 0.2, 0]                # beat a expected-score number
LBL_POS    = [3.1, 1.4, 0]               # its caption
NUM_FS     = 48
LBL_FS     = 34
TWO_L      = [-3.95, 0, 0]               # two-card centres (beats c, e)
TWO_R      = [3.95, 0, 0]
COL4_W     = 0.8                         # narrow 4th "bonus" column

# bonus-point tier colours — SAME as scene 07's summary panel
BONUS_COLOR = {1: ACCENT_GOLD, 2: ACCENT_FILL, 4: ACCENT_RED}


def _sgn(d):
    return f"+{d}" if d > 0 else ("0" if d == 0 else f"−{-d}")


class TwoPlayer(YahtzeeScene):
    """Scene 12 — telling who's winning in a 2-player game.

      a expected_score   — 12 in a box changes your EXPECTED total wildly
      b simplified_score  — bring back the 4/2/1 bonus point system
      c compare_cards     — two full cards; +1 bonus pt beats a higher raw score
      d remaining_boxes   — judging open boxes: pace markers + faded 0/1/2
      e ahead_behind      — ahead -> secure; behind -> go big
    """

    def setup_scene(self):
        # Scene 12 follows a talking head (THI); nothing on screen at frame 0.
        pass

    # ── shared bonus-column helpers ──────────────────────────────────────────
    def _c4_text(self, s, x, y, color, *, fs=SCORECARD_FONT_SIZE * 0.9, op=1.0):
        return crisp_text(s, font=FONT, font_size=fs, color=color,
                          weight="BOLD").move_to([x, y, 0]).set_opacity(op)

    def _c4_group(self, card, scores, *, show_total=True):
        """Column-4 bonus-point numbers for a card: one per earned bonus (tier
        coloured like scene 07), plus the running total in the footer (white, to
        match the Total row text)."""
        top_sum = sum(s for s in scores[0:6] if s is not None)
        entries = []                                  # (key, points)
        if top_sum >= 63:
            entries.append(("TOP", 2))
        for r, ok, pts in [(R_3K, scores[6], 1), (R_4K, scores[7], 1),
                           (R_FH, scores[8] == 25, 1), (R_SS, scores[9] == 30, 1),
                           (R_LS, scores[10] == 40, 2), (R_YZ, scores[11] == 50, 2)]:
            if ok:
                entries.append((r, pts))
        yb = scores[13] or 0
        total = sum(p for _, p in entries) + 4 * (yb // 100)

        x = card.col4_cells[0].get_center()[0]
        g = VGroup()
        for key, pts in entries:
            y = (card.col4_region(range(6))[0][1] if key == "TOP"
                 else card.col4_cells[key].get_center()[1])
            g.add(self._c4_text(str(pts), x, y, BONUS_COLOR[pts]))
        if show_total:
            g.add(self._c4_text(str(total), x, card.total_text.get_center()[1], WHITE))
        return g

    # ════════════════════════════════════════════════════════════════════════
    # a) same 12 points, three very different expected totals
    # ════════════════════════════════════════════════════════════════════════
    def _setup_expected(self):
        # a "blank scorecard" = the start of the game: a NORMAL card (3rd column
        # present, totals at 0), not a card with its summary column stripped.
        self.card = get_scorecard(scores=[None] * 14, center=CARD_L_POS)
        self.ev_label = crisp_text("Expected score:", font=FONT, font_size=LBL_FS,
                                   color=BLACK, weight="BOLD").move_to(LBL_POS)
        self.ev_tr = ValueTracker(EV_START)

    def _ev_number(self):
        v = self.ev_tr.get_value()
        if abs(v - EV_START) < 1e-6:            # start black, then colour by result
            col = BLACK
        else:
            col = SCORE_GREEN if v > EV_START else SCORE_RED
        return crisp_text(f"{v:.1f}", font=FONT, font_size=NUM_FS, color=col,
                          weight="BOLD").move_to(NUM_POS)

    @subscene
    def expected_score(self):
        self._setup_expected()
        in_rt, count_rt, hold = 1.0, 0.8, 0.7

        ev_live = always_redraw(self._ev_number)
        self.play(FadeIn(self.card, shift=RIGHT * 0.5),
                  FadeIn(self.ev_label, shift=UP * 0.2),
                  FadeIn(ev_live), run_time=in_rt)
        self.wait(0.4)

        # each example is INDEPENDENT (same 12 from the start): fill the box (the
        # card's own total ticks too), then the expected-score number re-counts.
        prev = None
        for row, ev in EV_STEPS:
            changes = {row: 12} if prev is None else {prev: None, row: 12}
            self.card.transition(self, changes, run_time=0.7)
            self.play(self.ev_tr.animate.set_value(ev), run_time=count_rt)
            self.wait(hold)
            prev = row

        # freeze the live number so the next beat can fade a static copy
        self.remove(ev_live)
        self.ev_num = self._ev_number()
        self.add(self.ev_num)
        self._last_box = prev

    # ════════════════════════════════════════════════════════════════════════
    # b) the simplified 4/2/1 bonus-point system
    # ════════════════════════════════════════════════════════════════════════
    def _right_card(self):
        fxr = self.camera.frame_width / 2
        left = self.card.get_right()[0] + GAP
        right = fxr - GAP
        c = get_card(right - left, self.card.height,
                     center=[(left + right) / 2, self.card.get_center()[1], 0])
        c.set_z_index(-1)
        return c

    def _setup_panel(self):
        H = SCORECARD_FONT_SIZE

        def header(t, color):
            return crisp_text(t, font=FONT, font_size=H * 0.95, color=color, weight="BOLD")

        def item(t):
            return crisp_text(t, font=FONT, font_size=H * 0.8, color=BLACK)

        items = [item("Each Extra Yahtzee"), item("Top Bonus"), item("Large Straight"),
                 item("Yahtzee"), item("3 of a Kind"), item("4 of a Kind"),
                 item("Full House"), item("Small Straight")]
        lines = [header("Giant Bonus (4 pts each)", ACCENT_RED), items[0],
                 header("Big Bonuses (2 pts each)", ACCENT_FILL), items[1], items[2], items[3],
                 header("Small Bonuses (1 pt each)", ACCENT_GOLD), items[4], items[5], items[6], items[7]]
        panel = VGroup(*lines).arrange(DOWN, aligned_edge=LEFT, buff=0.24)
        for it in items:
            it.shift(RIGHT * 0.45)

        self.panel_card = self._right_card()
        panel.scale(self.panel_card.height * 0.86 / panel.height)
        panel.move_to(self.panel_card.get_center())
        self.panel = panel

    @subscene
    def simplified_score(self):
        clear_rt, in_rt = 0.6, 1.0
        # clear the score sheet (the 12 leaves) and the expected-score readout
        self.play(FadeOut(self.ev_num, shift=UP * 0.2),
                  FadeOut(self.ev_label, shift=UP * 0.2), run_time=clear_rt)
        self.card.transition(self, {self._last_box: None}, run_time=clear_rt)
        self.ev_num = self.ev_label = None

        self._setup_panel()
        self.play(FadeIn(self.panel_card), FadeIn(self.panel, shift=RIGHT * 0.4),
                  run_time=in_rt)

    # ════════════════════════════════════════════════════════════════════════
    # c) two full cards: +1 bonus point ⇒ 97% they also won
    # ════════════════════════════════════════════════════════════════════════
    def _setup_compare(self):
        self.cA = get_scorecard(scores=CARD_A, center=TWO_L,
                                fourth_column=True, fourth_width=COL4_W)
        self.cB = get_scorecard(scores=CARD_B, center=TWO_R,
                                fourth_column=True, fourth_width=COL4_W)
        self.c4A = self._c4_group(self.cA, CARD_A)
        self.c4B = self._c4_group(self.cB, CARD_B)

    @subscene
    def compare_cards(self):
        self._setup_compare()
        out_rt, in_rt, num_rt, hold = 0.6, 0.9, 0.6, 1.2

        self.play(FadeOut(self.card, shift=LEFT * 0.4),
                  FadeOut(self.panel), FadeOut(self.panel_card), run_time=out_rt)
        self.card = self.panel = self.panel_card = None

        self.play(FadeIn(self.cA, shift=RIGHT * 0.4),
                  FadeIn(self.cB, shift=LEFT * 0.4), run_time=in_rt)
        self.play(FadeIn(self.c4A), FadeIn(self.c4B), run_time=num_rt)

        highlight(self, [self.c4A, self.c4B], hold=hold)          # bonus columns
        highlight(self, [self.cA.total_text, self.cB.total_text], hold=hold)  # totals

    # ════════════════════════════════════════════════════════════════════════
    # d) judging the open boxes: pace markers + faded 0/1/2
    # ════════════════════════════════════════════════════════════════════════
    def _gap_y(self, card):
        return (card.col4_cells[5].get_bottom()[1] + card.col4_cells[6].get_top()[1]) / 2

    def _col4_text(self, card, row, s, *, opacity=1.0):
        x = card.col4_cells[0].get_center()[0]
        y = card.col4_cells[row].get_center()[1]
        return self._c4_text(s, x, y, BLACK, op=opacity)

    def _dev_text(self, card, row, dev):
        # ±x pace marker in the roomy right side of the LABEL column, just to the
        # LEFT of the value number (keeps clear of the 3rd-column (63) bar)
        x = card.value_cells[row].get_left()[0] - 0.15
        y = card.value_cells[row].get_center()[1]
        t = crisp_text(_sgn(dev), font=FONT, font_size=SCORECARD_FONT_SIZE * 0.62,
                       color=BLACK, weight="BOLD")
        return t.move_to([x, y, 0], aligned_edge=RIGHT)

    def _setup_remaining(self):
        # A blank card = mid-game, 3rd column present (the (63) bar). The pace
        # markers sit in column 1, left of the value numbers.
        self.cD = get_scorecard(scores=CARD_D, center=CENTER_SC,
                                fourth_column=True, fourth_width=COL4_W)
        # faded expected bonus points for the OPEN boxes (col 4)
        self.d_yz0 = self._col4_text(self.cD, R_YZ, "0", opacity=0.4)
        self.d_ss1 = self._col4_text(self.cD, R_SS, "1", opacity=0.4)
        # ±x pace markers (right of column 2) + their sum in the section gap
        self.d_devs = VGroup(*[self._dev_text(self.cD, r, d) for r, d in D_TOP_DEVS.items()])
        gx = self.cD.value_cells[0].get_left()[0] - 0.15
        gy = self._gap_y(self.cD)
        self.d_sum = crisp_text(_sgn(sum(D_TOP_DEVS.values())), font=FONT,
                                font_size=SCORECARD_FONT_SIZE * 0.7, color=BLACK,
                                weight="BOLD").move_to([gx, gy, 0], aligned_edge=RIGHT)
        # gray "2" in the MIDDLE of the col-4 top section (expected top bonus)
        tc = self.cD.col4_region(range(6))[0]
        self.d_top2 = self._c4_text("2", tc[0], tc[1], BLACK, op=0.4)

    @subscene
    def remaining_boxes(self):
        self._setup_remaining()
        out_rt, in_rt, step, hold = 0.6, 0.9, 0.5, 0.8

        self.play(FadeOut(self.cA, shift=LEFT * 0.4), FadeOut(self.cB, shift=RIGHT * 0.4),
                  FadeOut(self.c4A), FadeOut(self.c4B), run_time=out_rt)
        self.cA = self.cB = self.c4A = self.c4B = None

        self.play(FadeIn(self.cD, shift=UP * 0.3), run_time=in_rt)

        self.cD.highlight_rows(self, [R_YZ], run_time=0.8)       # open Yahtzee -> 0
        self.play(FadeIn(self.d_yz0), run_time=step)
        self.cD.highlight_rows(self, [R_SS], run_time=0.8)       # open SmS -> 1
        self.play(FadeIn(self.d_ss1), run_time=step)

        self.play(FadeIn(self.d_devs, lag_ratio=0.3), run_time=1.0)   # ±x per top box
        self.wait(0.2)
        self.play(FadeIn(self.d_sum), run_time=step)                  # their sum (+5)
        self.play(FadeIn(self.d_top2), run_time=step)                 # -> gray 2
        self.wait(hold)

    # ════════════════════════════════════════════════════════════════════════
    # e) ahead -> secure sure points; behind -> go big
    # ════════════════════════════════════════════════════════════════════════
    def _setup_ahead(self):
        self.eL = get_scorecard(scores=CARD_L, center=TWO_L,
                                fourth_column=True, fourth_width=COL4_W)
        self.eR = get_scorecard(scores=CARD_R, center=TWO_R,
                                fourth_column=True, fourth_width=COL4_W)
        self.e4L = self._c4_group(self.eL, CARD_L)
        self.e4R = self._c4_group(self.eR, CARD_R)

    @subscene
    def ahead_behind(self):
        self._setup_ahead()
        out_rt, in_rt, num_rt, zero_rt = 0.6, 0.9, 0.5, 0.8

        clutter = [self.cD, self.d_yz0, self.d_ss1, self.d_devs, self.d_sum, self.d_top2]
        self.play(*[FadeOut(m) for m in clutter], run_time=out_rt)
        self.cD = None

        self.play(FadeIn(self.eL, shift=RIGHT * 0.4),
                  FadeIn(self.eR, shift=LEFT * 0.4), run_time=in_rt)
        self.play(FadeIn(self.e4L), FadeIn(self.e4R), run_time=num_rt)
        highlight(self, [self.e4L, self.e4R], hold=1.0)         # left is ahead on bonuses

        # LEFT (ahead): lock in easy points, then it's fine to zero the Yahtzee
        self.eL.highlight_rows(self, [R_SS], run_time=0.9)
        self.eL.highlight_rows(self, TOP_ROWS, run_time=1.0)
        self.eL.transition(self, {R_YZ: 0}, run_time=zero_rt)

        # RIGHT (behind): keep the Yahtzee alive, sacrifice ones then 4 of a kind
        self.eR.highlight_rows(self, [R_YZ], run_time=0.9)
        self.eR.transition(self, {0: 0}, run_time=zero_rt)
        self.eR.transition(self, {R_4K: 0}, run_time=zero_rt)
