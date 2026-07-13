from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from bpkfigures.style import ACCENT_GOLD, ACCENT_FILL, ACCENT_RED
from bpkfigures.card import get_card
from bpkfigures.highlight import overlay_rect
from assets.scorecard import get_scorecard, get_two_scorecards, slide_two_in


# ══ numbers (all SOURCED — see math/scene12_numbers.py) ═══════════════════════
#   start        = V(empty)                 = 254.6
#   after 3 box  = 12 + V(Threes=12)        = 257.4  (four 3s — a GOOD turn)
#   after 4 kind = 12 + V(4Kind=12)         = 247.5  (pretty bad)
#   after 6 box  = 12 + V(Sixes=12, two 6s) = 232.2  (really bad)
EV_START = 254.6
EV_STEPS = [(2, 257.4), (7, 247.5), (5, 232.2)]   # (scorecard row, expected total)

# ── example scorecards (row order = SCORE_ROWS; 13 = yahtzee bonus) ────────────
#   0-5 Ones..Sixes | 6 3ofK | 7 4ofK | 8 FH | 9 SmS | 10 LgS | 11 Yz | 12 Ch | 13 yb
# Beat c: A wins by 1 bonus pt AND on total (263/8 vs 252/7); each misses a bonus
# the other has (A: no LgS; B: no 4ofK, no Yz), yet the LOSER (B) leads in raw top
# section, 3-kind and chance.
CARD_A = [3, 6, 9, 12, 15, 18, 18, 22, 25, 30,  0, 50, 20, 0]
CARD_B = [3, 8, 12, 12, 15, 18, 26,  0, 25, 30, 40,  0, 28, 0]
# Beat d: full except Fours(3)/Sixes(5)/SmS(9)/Yahtzee(11); top devs sum to +5.
CARD_D = [1, 8, 9, None, 20, None, 20, 18, 25, None, 40, None, 22, 0]
D_TOP_DEVS = {0: -2, 1: +2, 2: 0, 4: +5}      # filled top box -> (score − 3×face)
# Beats e/f: two mid-game 4-col cards with the SAME number of boxes filled (9
# each). LEFT is ahead (expected final ~269 vs ~232 — see scene12_numbers).
# RIGHT's top outside 1s/6s is 44, so zeroing the 1s (vs a modest 3) raises the
# bonus from THREE sixes (44+3+18=65) to FOUR (44+0+18=62<63; needs 24) — the 1s
# decision legitimately changes the sixes you need.
CARD_L = [3, 6, 9, 12, 15, 18, None, 28, 25, None, 40, None, None, 0]   # open: 3ofK,SmS,Yz,Ch
CARD_R = [None, 8, 9, 12, 15, None, 18, None, 25, 30, 40, None, 15, 0]   # top 44; open: Ones,Sixes,4ofK,Yz

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
# TWO_L/TWO_R (the two-card centres) now come from assets.scorecard via
# get_two_scorecards — the shared two-card convention.
COL4_W     = 0.8                         # narrow 4th "bonus" column

# bonus-point tier colours — SAME as scene 07's summary panel
BONUS_COLOR = {1: ACCENT_GOLD, 2: ACCENT_FILL, 4: ACCENT_RED}
FADED_OP    = 0.45                        # faded 4th-column expectations


def _sgn(d):
    return f"+{d}" if d > 0 else ("0" if d == 0 else f"−{-d}")


class TwoPlayer(YahtzeeScene):
    """Scene 12 — telling who's winning in a 2-player game.

      a expected_score   — 12 in a box changes your EXPECTED total wildly
      b simplified_score  — bring back the 4/2/1 bonus point system
      c compare_cards     — two full cards; +1 bonus pt beats a higher raw score
      d remaining_boxes   — judging open boxes: pace markers + faded 0/1/2
      e ahead             — if you're ahead: secure sure points, zero the Yahtzee
      f behind            — if you're behind: keep the Yahtzee, zero ones / 4-kind
    """

    def setup_scene(self):
        # Scene 12 follows a talking head (THI); nothing on screen at frame 0.
        pass

    # ── play the card's box/bar changes IN ONE play with `extra` anims ────────
    def _card_and(self, card, changes, extra, run_time, *, flash=True):
        """Like Scorecard.transition, but the box/bar changes run together with
        the `extra` animations in a single play (patterned on scene 09)."""
        lead = list(extra)
        new_top, new_bot = card._top_sum, card._bottom_sum
        for row, val in changes.items():
            old_val = card.value_nums.get(row, 0)
            delta = (0 if val is None else val) - old_val
            if row < 6:
                new_top += delta
            else:
                new_bot += delta
            num = card.value_texts.get(row)
            if val is None:
                if num is not None:
                    lead.append(FadeOut(num))
                card.value_texts.pop(row, None)
                card.value_nums.pop(row, None)
            else:
                bt = crisp_text(str(val), font_size=card.font_size, color=BLACK,
                                font=FONT).move_to(card.value_cells[row].get_center())
                if num is not None:
                    lead.append(Transform(num, bt))
                else:
                    lead.append(FadeIn(bt))
                    card.value_texts[row] = bt
                card.value_nums[row] = val
        card._animate_to(self, top=new_top, bottom=new_bot,
                         lead=AnimationGroup(*lead) if lead else None,
                         run_time=run_time, flash=flash)

    # ── shared bonus-column helpers ──────────────────────────────────────────
    def _c4_text(self, s, x, y, color, *, fs=SCORECARD_FONT_SIZE * 0.9, op=1.0):
        return crisp_text(s, font=FONT, font_size=fs, color=color,
                          weight="BOLD").move_to([x, y, 0]).set_opacity(op)

    def _c4_group(self, card, scores, *, show_total=True):
        """Column-4 bonus-point numbers: one per earned bonus (tier coloured like
        scene 07), plus the running total in the footer (white, matching the
        Total row text)."""
        top_sum = sum(s for s in scores[0:6] if s is not None)
        entries = []
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

    # ── full-column highlight regions (center, w, h) ─────────────────────────
    def _col_region(self, card, xc, w):
        top = card.value_cells[0].get_top()[1]
        bot = card.total_text.get_center()[1] - card.cell_height * 0.6
        return ([xc, (top + bot) / 2, 0], w, top - bot)

    def _col4_region(self, card):
        c = card.col4_cells[0]
        return self._col_region(card, c.get_center()[0], c.width)

    def _col3_region(self, card):
        left = card.value_cells[0].get_right()[0]
        right = card.col4_cells[0].get_left()[0]
        return self._col_region(card, (left + right) / 2, right - left)

    def _col_highlight(self, regions, *, hold=1.2, fade=0.25):
        """Highlight full columns with the tint sitting ABOVE everything (the
        scorecard's number texts are z=1, so a default-z overlay would tint the
        bar fill but leave the numbers floating on top — uneven)."""
        rects = [overlay_rect(r) for r in regions]
        for r in rects:
            r.set_z_index(10)
        self.play(*[FadeIn(r) for r in rects], run_time=fade)
        self.wait(hold)
        self.play(*[FadeOut(r) for r in rects], run_time=fade)
        self.remove(*rects)

    # ════════════════════════════════════════════════════════════════════════
    # a) same 12 points, three very different expected totals
    # ════════════════════════════════════════════════════════════════════════
    def _setup_expected(self):
        # a "blank scorecard" = the start of the game: a NORMAL card (3rd column
        # present, totals at 0).
        self.card = get_scorecard(scores=[None] * 14, center=CARD_L_POS)
        # counter + bar move TOGETHER (no lead/lag): the expected-score number
        # and the top bar animate simultaneously.
        self.card.COUNTER_LAG = 0.0
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

        ev_live = always_redraw(self._ev_number)
        self.play(self.card.slide_in(self, play=False),
                  FadeIn(self.ev_label, shift=UP * 0.2),
                  FadeIn(ev_live), run_time=1.0)
        self.wait(0.4)

        # Each example is INDEPENDENT (same 12 from the start) and pairs with its
        # OWN line of voiceover, so the steps are UNROLLED (not a loop) — each keeps
        # a run_time + wait you can tune on its own to match what's being said. The
        # box fill, the card's bar/total, and the counter all move in ONE play per
        # example. Numbers stay SOURCED from EV_STEPS (see the header block).
        (r_good, ev_good), (r_bad, ev_bad), (r_worst, ev_worst) = EV_STEPS
        # a1) four 3's → Threes = 12 (a GOOD turn: 254.6 → 257.4)
        self._card_and(self.card, {r_good: 12},
                       [self.ev_tr.animate.set_value(ev_good)], run_time=1.1)
        self.wait(0.7)
        # a2) four of a kind → 4-of-a-Kind = 12 (pretty bad: → 247.5)
        self._card_and(self.card, {r_good: None, r_bad: 12},
                       [self.ev_tr.animate.set_value(ev_bad)], run_time=1.1)
        self.wait(0.7)
        # a3) two 6's → Sixes = 12 (really bad: → 232.2)
        self._card_and(self.card, {r_bad: None, r_worst: 12},
                       [self.ev_tr.animate.set_value(ev_worst)], run_time=1.1)
        self.wait(0.7)

        self.remove(ev_live)
        self.ev_num = self._ev_number()
        self.add(self.ev_num)
        self._last_box = r_worst

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
        self._setup_panel()
        # clear the sheet, drop the readout, and bring the panel in — ALL together
        # (don't wait for the bar to clear before the panel appears).
        self._card_and(self.card, {self._last_box: None},
                       [FadeOut(self.ev_num, shift=UP * 0.2),
                        FadeOut(self.ev_label, shift=UP * 0.2),
                        FadeIn(self.panel_card),
                        FadeIn(self.panel, shift=RIGHT * 0.4)],
                       run_time=1.0)
        self.ev_num = self.ev_label = None

    # ════════════════════════════════════════════════════════════════════════
    # c) two full cards: +1 bonus point ⇒ 97% they also won
    # ════════════════════════════════════════════════════════════════════════
    def _setup_compare(self):
        self.cA, self.cB = get_two_scorecards(CARD_A, CARD_B,
                                              fourth_column=True, fourth_width=COL4_W)
        self.c4A = self._c4_group(self.cA, CARD_A)
        self.c4B = self._c4_group(self.cB, CARD_B)

    @subscene
    def compare_cards(self):
        self._setup_compare()
        hold = 1.2

        self.play(FadeOut(self.card, shift=LEFT * 0.4),
                  FadeOut(self.panel), FadeOut(self.panel_card), run_time=0.6)
        self.card = self.panel = self.panel_card = None

        slide_two_in(self, self.cA, self.cB, run_time=0.9)
        self.play(FadeIn(self.c4A), FadeIn(self.c4B), run_time=0.6)

        # highlight the WHOLE 4th column, then the WHOLE 3rd column, on both cards
        self._col_highlight([self._col4_region(self.cA), self._col4_region(self.cB)], hold=hold)
        self._col_highlight([self._col3_region(self.cA), self._col3_region(self.cB)], hold=hold)

    # ════════════════════════════════════════════════════════════════════════
    # d) judging the open boxes: pace markers + faded 0/1/2
    # ════════════════════════════════════════════════════════════════════════
    def _gap_y(self, card):
        return (card.col4_cells[5].get_bottom()[1] + card.col4_cells[6].get_top()[1]) / 2

    def _c4_faded(self, card, row, s, color):
        x = card.col4_cells[0].get_center()[0]
        y = card.col4_cells[row].get_center()[1]
        return self._c4_text(s, x, y, color, op=FADED_OP)

    def _dev_text(self, card, row, dev):
        # ±x pace marker in the roomy right side of the LABEL column, just LEFT of
        # the value number (clear of the 3rd-column (63) bar)
        x = card.value_cells[row].get_left()[0] - 0.15
        y = card.value_cells[row].get_center()[1]
        t = crisp_text(_sgn(dev), font=FONT, font_size=SCORECARD_FONT_SIZE * 0.62,
                       color=BLACK, weight="BOLD")
        return t.move_to([x, y, 0], aligned_edge=RIGHT)

    def _setup_remaining(self):
        self.cD = get_scorecard(scores=CARD_D, center=CENTER_SC,
                                fourth_column=True, fourth_width=COL4_W)
        # faded, tier-coloured expectations for the OPEN boxes (col 4)
        self.d_yz0 = self._c4_faded(self.cD, R_YZ, "0", ACCENT_FILL)   # Yahtzee (big)
        self.d_ss1 = self._c4_faded(self.cD, R_SS, "1", ACCENT_GOLD)   # Sm Straight (small)
        # ±x pace markers (label column) + their sum in the section gap
        self.d_devs = VGroup(*[self._dev_text(self.cD, r, d) for r, d in D_TOP_DEVS.items()])
        gx = self.cD.value_cells[0].get_left()[0] - 0.15
        gy = self._gap_y(self.cD)
        self.d_sum = crisp_text(_sgn(sum(D_TOP_DEVS.values())), font=FONT,
                                font_size=SCORECARD_FONT_SIZE * 0.7, color=BLACK,
                                weight="BOLD").move_to([gx, gy, 0], aligned_edge=RIGHT)
        # faded blue "2" in the MIDDLE of the col-4 top section (expected top bonus)
        tc = self.cD.col4_region(range(6))[0]
        self.d_top2 = self._c4_text("2", tc[0], tc[1], ACCENT_FILL, op=FADED_OP)

    @subscene
    def remaining_boxes(self):
        self._setup_remaining()
        step = 0.5

        self.play(FadeOut(self.cA, shift=LEFT * 0.4), FadeOut(self.cB, shift=RIGHT * 0.4),
                  FadeOut(self.c4A, shift=LEFT * 0.4), FadeOut(self.c4B, shift=RIGHT * 0.4),
                  run_time=0.6)
        self.cA = self.cB = self.c4A = self.c4B = None

        self.play(self.cD.slide_in(self, from_dir=DOWN, play=False), run_time=0.9)

        self.cD.highlight_rows(self, [R_YZ], run_time=0.8)       # open Yahtzee -> 0
        self.play(FadeIn(self.d_yz0), run_time=step)
        self.cD.highlight_rows(self, [R_SS], run_time=0.8)       # open SmS -> 1
        self.play(FadeIn(self.d_ss1), run_time=step)

        self.play(FadeIn(self.d_devs, lag_ratio=0.3), run_time=1.0)   # ±x per top box
        self.wait(0.2)
        self.play(FadeIn(self.d_sum), run_time=step)                  # their sum (+5)
        self.play(FadeIn(self.d_top2), run_time=step)                 # -> faded 2
        self.wait(0.8)

    # ════════════════════════════════════════════════════════════════════════
    # e/f) ahead -> secure sure points ; behind -> go big
    # ════════════════════════════════════════════════════════════════════════
    def _zero_flash(self, card, row, *, hold=0.9, fade=0.28):
        """Zero a box for illustration: highlight the row, show the 0 ONLY while
        it's highlighted, then clear both (the example card is left untouched)."""
        fill, border, bold = card._row_highlight(row, ACCENT_GOLD, 0.45)
        zero = crisp_text("0", font_size=card.font_size, color=BLACK,
                          font=FONT).move_to(card.value_cells[row].get_center())
        card.labels[row].save_state()
        self.play(FadeIn(fill), FadeIn(border),
                  Transform(card.labels[row], bold), FadeIn(zero), run_time=fade)
        self.wait(hold)
        self.play(FadeOut(fill), FadeOut(border),
                  Restore(card.labels[row]), FadeOut(zero), run_time=fade)
        self.remove(fill, border, zero)

    def _setup_two(self):
        self.eL, self.eR = get_two_scorecards(CARD_L, CARD_R,
                                              fourth_column=True, fourth_width=COL4_W)
        self.e4L = self._c4_group(self.eL, CARD_L)
        self.e4R = self._c4_group(self.eR, CARD_R)

    @subscene
    def ahead(self):
        self._setup_two()

        clutter = [self.cD, self.d_yz0, self.d_ss1, self.d_devs, self.d_sum, self.d_top2]
        self.play(*[FadeOut(m) for m in clutter], run_time=0.6)
        self.cD = None

        slide_two_in(self, self.eL, self.eR, run_time=0.9)
        self.play(FadeIn(self.e4L), FadeIn(self.e4R), run_time=0.5)

        # LEFT (ahead): lock in easy points, then it's fine to zero the Yahtzee
        self.eL.highlight_rows(self, [R_SS], run_time=0.9)
        self.eL.highlight_rows(self, TOP_ROWS, run_time=1.0)
        self._zero_flash(self.eL, R_YZ)

    @subscene
    def behind(self):
        # RIGHT (behind): keep the Yahtzee alive, sacrifice ones then 4 of a kind
        self.eR.highlight_rows(self, [R_YZ], run_time=0.9)
        self._zero_flash(self.eR, 0)
        self._zero_flash(self.eR, R_4K)
