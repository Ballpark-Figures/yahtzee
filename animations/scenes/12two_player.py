from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from bpkfigures.style import ACCENT_GOLD, ACCENT_FILL, ACCENT_RED
from bpkfigures.card import get_card
from assets.scorecard import get_scorecard


# ══ numbers (all SOURCED — see math/scene12_numbers.py) ═══════════════════════
#   start        = V(empty)                      = 254.6
#   after 3 box  = 12 + V(Threes=12)             = 257.4  (four 3s — a GOOD turn)
#   after 4 kind = 12 + V(4Kind=12)              = 247.5  (pretty bad)
#   after 6 box  = 12 + V(Sixes=12, two 6s)      = 232.2  (really bad)
EV_START = 254.6
EV_STEPS = [
    (2,  257.4),   # 12 in the 3 box  (scorecard row 2 = Threes)
    (7,  247.5),   # 12 in 4 of a Kind (row 7)
    (5,  232.2),   # 12 in the 6 box  (row 5 = Sixes)
]

# ── example scorecards (row order = SCORE_ROWS; 13 = yahtzee bonus) ────────────
#   0-5 Ones..Sixes | 6 3ofK | 7 4ofK | 8 FH | 9 SmS | 10 LgS | 11 Yz | 12 Ch | 13 yb
# Beat c: A beats B by exactly 1 bonus pt AND on total (312/10 vs 281/9).
CARD_A = [3, 6, 9, 12, 15, 18, 21, 24, 25, 30, 40, 50, 24, 0]
CARD_B = [1, 4, 9, 16, 15, 18, 18,  0, 25, 30, 40, 50, 20, 0]
A_BONUS_PTS, B_BONUS_PTS = 10, 9
# Beat d: full except Fours(3)/Sixes(5)/SmS(9)/Yahtzee(11); top devs sum to +5.
CARD_D = [1, 8, 9, None, 20, None, 20, 18, 25, None, 40, None, 22, 0]
D_TOP_DEVS = {0: -2, 1: +2, 2: 0, 4: +5}      # filled top box -> (score − 3×face)
# Beat e: two mid-game cards; LEFT clearly ahead (229/7 vs 188/5).
CARD_L = [3, 6, 9, 12, 15, 18, 22, 24, 25, None, 40, None, 20, 0]   # open: SmS, Yz
CARD_R = [None, 6, 9, 12, 15, 18, 18, None, 25, 30, 40, None, 15, 0]  # open: Ones, 4K, Yz

# ── scorecard row indices (asset convention) ──────────────────────────────────
R_3K, R_4K, R_FH, R_SS, R_LS, R_YZ, R_CH = 6, 7, 8, 9, 10, 11, 12
TOP_ROWS = list(range(6))

# ── layout ────────────────────────────────────────────────────────────────────
CARD_L_POS = [-4.4, 0, 0]                # beat a/b card (left)
NUM_POS    = [3.1, 0.2, 0]               # beat a expected-score number
LBL_POS    = [3.1, 1.35, 0]              # its caption
NUM_FS     = 48
LBL_FS     = 34
TWO_L      = [-3.95, 0, 0]               # two-card centres (beats c, e)
TWO_R      = [3.95, 0, 0]
COL4_W     = 0.8                         # narrow 4th "bonus" column


def _sgn(d):
    return f"+{d}" if d > 0 else ("0" if d == 0 else f"−{-d}")


class TwoPlayer(YahtzeeScene):
    """Scene 12 — telling who's winning in a 2-player game.

      a expected_score   — 12 in a box changes your EXPECTED total wildly
      b simplified_score  — bring back the 4/2/1 bonus point system
      c compare_cards     — two full cards; +1 bonus pt tracks the higher total
      d remaining_boxes   — judging open boxes: faded 0/1/2 + top-section pace
      e ahead_behind      — ahead -> secure; behind -> go big
    """

    def setup_scene(self):
        # Scene 12 follows a talking head (THI); nothing on screen at frame 0.
        pass

    # ════════════════════════════════════════════════════════════════════════
    # a) same 12 points, three very different expected totals
    # ════════════════════════════════════════════════════════════════════════
    def _setup_expected(self):
        self.card = get_scorecard(scores=[None] * 14, center=CARD_L_POS,
                                  show_summary=False)
        self.ev_label = crisp_text("Expected score:", font=FONT, font_size=LBL_FS,
                                   color=BLACK, weight="BOLD").move_to(LBL_POS)
        self.ev_tr = ValueTracker(EV_START)
        self.twelve = crisp_text("12", font=FONT, font_size=SCORECARD_FONT_SIZE,
                                 color=BLACK)

    def _ev_number(self):
        v = self.ev_tr.get_value()
        col = SCORE_GREEN if v >= EV_START - 1e-6 else SCORE_RED
        return crisp_text(f"{v:.1f}", font=FONT, font_size=NUM_FS, color=col,
                          weight="BOLD").move_to(NUM_POS)

    @subscene
    def expected_score(self):
        self._setup_expected()
        in_rt, fill_rt, move_rt, hold = 0.9, 1.0, 0.9, 0.7

        ev_live = always_redraw(self._ev_number)
        self.play(FadeIn(self.card, shift=RIGHT * 0.5),
                  FadeIn(self.ev_label, shift=UP * 0.2),
                  FadeIn(ev_live), run_time=in_rt)
        self.wait(0.3)

        # first box: fade the 12 into the 3 box while the number climbs to 257.4
        row0, ev0 = EV_STEPS[0]
        self.twelve.move_to(self.card.value_cells[row0].get_center())
        self.play(FadeIn(self.twelve),
                  self.ev_tr.animate.set_value(ev0), run_time=fill_rt)
        self.wait(hold)

        # then MOVE the same 12 to the next box, re-counting each time
        for row, ev in EV_STEPS[1:]:
            self.play(self.twelve.animate.move_to(self.card.value_cells[row].get_center()),
                      self.ev_tr.animate.set_value(ev), run_time=move_rt)
            self.wait(hold)

        # freeze the live number so the next beat can fade a static copy
        self.remove(ev_live)
        self.ev_num = self._ev_number()
        self.add(self.ev_num)

    # ════════════════════════════════════════════════════════════════════════
    # b) the simplified 4/2/1 bonus-point system
    # ════════════════════════════════════════════════════════════════════════
    def _setup_panel(self):
        H = SCORECARD_FONT_SIZE

        def header(t, color):
            return crisp_text(t, font=FONT, font_size=H * 0.95, color=color, weight="BOLD")

        def item(t):
            return crisp_text(t, font=FONT, font_size=H * 0.8, color=BLACK)

        headers = [header("Giant Bonus (4 pts each)", ACCENT_RED),
                   header("Big Bonuses (2 pts each)", ACCENT_FILL),
                   header("Small Bonuses (1 pt each)", ACCENT_GOLD)]
        items = [item("Each Extra Yahtzee"),
                 item("Top Bonus"), item("Large Straight"), item("Yahtzee"),
                 item("3 of a Kind"), item("4 of a Kind"),
                 item("Full House"), item("Small Straight")]
        lines = [headers[0], items[0],
                 headers[1], items[1], items[2], items[3],
                 headers[2], items[4], items[5], items[6], items[7]]
        panel = VGroup(*lines).arrange(DOWN, aligned_edge=LEFT, buff=0.24)
        for it in items:                      # indent the item rows under headers
            it.shift(RIGHT * 0.45)

        self.panel_card = get_card(5.7, self.card.height * 0.94, center=[3.1, 0, 0])
        self.panel_card.set_z_index(-1)
        panel.scale(self.panel_card.height * 0.84 / panel.height)
        panel.move_to(self.panel_card.get_center())
        self.panel = panel

    @subscene
    def simplified_score(self):
        clear_rt, in_rt = 0.6, 1.0
        # clear the score sheet: the 12 and the expected-score readout leave
        self.play(FadeOut(self.twelve),
                  FadeOut(self.ev_num, shift=UP * 0.2),
                  FadeOut(self.ev_label, shift=UP * 0.2), run_time=clear_rt)
        self.twelve = self.ev_num = self.ev_label = None

        self._setup_panel()
        self.play(FadeIn(self.panel_card), FadeIn(self.panel, shift=RIGHT * 0.4),
                  run_time=in_rt)

    # ════════════════════════════════════════════════════════════════════════
    # c) two full cards: +1 bonus point ⇒ 97% they also won
    # ════════════════════════════════════════════════════════════════════════
    def _c4_group(self, card, scores, bonus_total):
        """Per-row bonus-point numbers in column 4, plus the total in the footer."""
        top_sum = sum(s for s in scores[0:6] if s is not None)
        rows = []
        if top_sum >= 63:
            rows.append(("TOP", "2"))
        for r, ok, pts in [(R_3K, scores[6], "1"), (R_4K, scores[7], "1"),
                           (R_FH, scores[8] == 25, "1"), (R_SS, scores[9] == 30, "1"),
                           (R_LS, scores[10] == 40, "2"), (R_YZ, scores[11] == 50, "2")]:
            if ok:
                rows.append((r, pts))
        rows.append(("TOTAL", str(bonus_total)))

        x = card.col4_cells[0].get_center()[0]
        g = VGroup()
        for key, s in rows:
            if key == "TOP":
                y = card.col4_region(range(6))[0][1]
            elif key == "TOTAL":
                y = card.total_text.get_center()[1]
            else:
                y = card.col4_cells[key].get_center()[1]
            g.add(crisp_text(s, font=FONT, font_size=SCORECARD_FONT_SIZE * 0.9,
                             color=BLACK, weight="BOLD").move_to([x, y, 0]))
        return g

    def _setup_compare(self):
        self.cA = get_scorecard(scores=CARD_A, center=TWO_L,
                                fourth_column=True, fourth_width=COL4_W)
        self.cB = get_scorecard(scores=CARD_B, center=TWO_R,
                                fourth_column=True, fourth_width=COL4_W)
        self.c4A = self._c4_group(self.cA, CARD_A, A_BONUS_PTS)
        self.c4B = self._c4_group(self.cB, CARD_B, B_BONUS_PTS)

    @subscene
    def compare_cards(self):
        self._setup_compare()
        out_rt, in_rt, num_rt, hold = 0.6, 0.9, 0.6, 1.2

        # the beat-b card + panel leave; the two full cards arrive
        self.play(FadeOut(self.card, shift=LEFT * 0.4),
                  FadeOut(self.panel), FadeOut(self.panel_card), run_time=out_rt)
        self.card = self.panel = self.panel_card = None

        self.play(FadeIn(self.cA, shift=RIGHT * 0.4),
                  FadeIn(self.cB, shift=LEFT * 0.4), run_time=in_rt)
        self.play(FadeIn(self.c4A), FadeIn(self.c4B), run_time=num_rt)

        # highlight both 4th (bonus) columns, then both grand totals
        highlight(self, [self.c4A, self.c4B], hold=hold)
        highlight(self, [self.cA.total_text, self.cB.total_text], hold=hold)

    # ════════════════════════════════════════════════════════════════════════
    # d) judging the open boxes: faded 0/1/2 + top-section pace
    # ════════════════════════════════════════════════════════════════════════
    def _summary_x(self, card):
        return (card.value_cells[0].get_right()[0] + card.col4_cells[0].get_left()[0]) / 2

    def _gap_y(self, card):
        return (card.col4_cells[5].get_bottom()[1] + card.col4_cells[6].get_top()[1]) / 2

    def _col4_text(self, card, row, s, *, opacity=1.0, color=BLACK):
        x = card.col4_cells[0].get_center()[0]
        y = card.col4_cells[row].get_center()[1]
        t = crisp_text(s, font=FONT, font_size=SCORECARD_FONT_SIZE * 0.9,
                       color=color, weight="BOLD").move_to([x, y, 0])
        return t.set_opacity(opacity)

    def _setup_remaining(self):
        self.cD = get_scorecard(scores=CARD_D, center=CENTER_SC, show_summary=False,
                                fourth_column=True, fourth_width=COL4_W)
        # faded expected bonus points for the OPEN boxes
        self.d_yz0 = self._col4_text(self.cD, R_YZ, "0", opacity=0.4)
        self.d_ss1 = self._col4_text(self.cD, R_SS, "1", opacity=0.4)
        # ±x pace markers for the filled top boxes, and their sum in the gap
        self.d_devs = VGroup(*[self._col4_text(self.cD, r, _sgn(d))
                               for r, d in D_TOP_DEVS.items()])
        gy = self._gap_y(self.cD)
        self.d_sum = crisp_text(_sgn(sum(D_TOP_DEVS.values())), font=FONT,
                                font_size=SCORECARD_FONT_SIZE * 0.95, color=BLACK,
                                weight="BOLD").move_to([self._summary_x(self.cD), gy, 0])
        self.d_top2 = crisp_text("2", font=FONT, font_size=SCORECARD_FONT_SIZE * 0.9,
                                 color=BLACK, weight="BOLD").move_to(
            [self.cD.col4_cells[0].get_center()[0], gy, 0]).set_opacity(0.4)

    @subscene
    def remaining_boxes(self):
        self._setup_remaining()
        out_rt, in_rt, step, hold = 0.6, 0.9, 0.5, 0.8

        self.play(FadeOut(self.cA, shift=LEFT * 0.4), FadeOut(self.cB, shift=RIGHT * 0.4),
                  FadeOut(self.c4A), FadeOut(self.c4B), run_time=out_rt)
        self.cA = self.cB = self.c4A = self.c4B = None

        self.play(FadeIn(self.cD, shift=UP * 0.3), run_time=in_rt)

        # open Yahtzee -> usually a 0
        self.cD.highlight_rows(self, [R_YZ], run_time=0.8)
        self.play(FadeIn(self.d_yz0), run_time=step)
        # open Small Straight -> usually still 1 point
        self.cD.highlight_rows(self, [R_SS], run_time=0.8)
        self.play(FadeIn(self.d_ss1), run_time=step)

        # top-section pace: ±x per filled box, then the sum, then the faded 2
        self.play(FadeIn(self.d_devs, lag_ratio=0.3), run_time=1.0)
        self.wait(0.2)
        self.play(FadeIn(self.d_sum), run_time=step)
        self.play(FadeIn(self.d_top2), run_time=step)
        self.wait(hold)

    # ════════════════════════════════════════════════════════════════════════
    # e) ahead -> secure sure points; behind -> go big
    # ════════════════════════════════════════════════════════════════════════
    def _setup_ahead(self):
        self.eL = get_scorecard(scores=CARD_L, center=TWO_L)
        self.eR = get_scorecard(scores=CARD_R, center=TWO_R)

    @subscene
    def ahead_behind(self):
        self._setup_ahead()
        out_rt, in_rt, zero_rt = 0.6, 0.9, 0.8

        clutter = [self.cD, self.d_yz0, self.d_ss1, self.d_devs, self.d_sum, self.d_top2]
        self.play(*[FadeOut(m) for m in clutter], run_time=out_rt)
        self.cD = None

        self.play(FadeIn(self.eL, shift=RIGHT * 0.4),
                  FadeIn(self.eR, shift=LEFT * 0.4), run_time=in_rt)
        # establish that the left card is ahead
        highlight(self, [self.eL.total_text, self.eR.total_text], hold=1.0)

        # LEFT (ahead): lock in easy points, then it's fine to zero the Yahtzee
        self.eL.highlight_rows(self, [R_SS], run_time=0.9)
        self.eL.highlight_rows(self, TOP_ROWS, run_time=1.0)
        self.eL.transition(self, {R_YZ: 0}, run_time=zero_rt)

        # RIGHT (behind): keep the Yahtzee alive, sacrifice ones then 4 of a kind
        self.eR.highlight_rows(self, [R_YZ], run_time=0.9)
        self.eR.transition(self, {0: 0}, run_time=zero_rt)
        self.eR.transition(self, {R_4K: 0}, run_time=zero_rt)
