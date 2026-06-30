from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from bpkfigures.style import FONT_SIZE_SM
from assets.scorecard import get_scorecard
from bpkfigures.histogram import get_histogram, overlay_bars, make_hist_legend
from bpkfigures.bar_graph import get_bar_graph
from assets import score_data as sd

# ── plot geometry / look (knobs for the user) ─────────────────────────────────
PLOT_C   = ORIGIN
PLOT_W   = 8.0
PLOT_H   = 4.0
MIN_PROB = 1e-4

BASE_COLOR   = "#1E335C"     # dark navy bars / +2 big-bonus numbers
BONUS1_COLOR = ORANGE        # one 100-pt yahtzee bonus
BONUS2_COLOR = RED           # two 100-pt yahtzee bonuses / +4 giant bonus
HL_COLOR     = "#E8A33D"     # peak-highlight colour / +1 small-bonus numbers

TOP_ROWS    = list(range(6))
CHANCE_ROW  = 12
YAHTZEE_ROW = 11


class Histogram(YahtzeeScene):
    def setup_scene(self):
        pass

    # ── shared builders ──────────────────────────────────────────────────────
    def _build_plot(self):
        return get_histogram(
            None, counts=self.base, min_prob=MIN_PROB,
            center=PLOT_C, width=PLOT_W, height=PLOT_H,
            bar_color=BASE_COLOR, bar_ratio=1.05, x_tick_step=50,
            show_y_axis=True, y_axis_label="Frequency (%)",
            x_axis_label="Score", title="Score Frequencies",
        )

    def _grow_up(self, bars, *extra, run_time=1.0):
        """Height-only grow: each bar rises from the axis (x fixed, no spreading
        out from the centre). ``extra`` animations play alongside."""
        for b in bars:
            b.save_state()
            b.stretch(1e-3, dim=1, about_edge=DOWN)
        self.play(*[Restore(b) for b in bars], *extra, run_time=run_time)

    def _card_behind(self, mob, pad=0.45, corner=0.22):
        card = RoundedRectangle(
            width=mob.width + 2 * pad, height=mob.height + 2 * pad,
            corner_radius=corner, fill_color=CARD_FILL, fill_opacity=1.0,
            stroke_color=BLACK, stroke_width=2)
        card.move_to(mob.get_center())
        card.set_z_index(-1)
        return card

    # ════════════════════════════════════════════════════════════════════════
    # a–c : the histogram and the two yahtzee-bonus overlays
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def show_plot(self, run_time=1.5):
        self.base = sd.score_distribution()
        self.plot = self._build_plot()
        self.overlay = VGroup()
        self.legend = None
        rest = VGroup(*[m for m in self.plot.submobjects if m is not self.plot.bars])
        self._grow_up(self.plot.bars, FadeIn(rest), run_time=run_time)
        self.wait(0.4)

    @subscene
    def overlay_one(self, run_time=1.0):
        o1 = sd.overlay_by_yahtzee(1)                 # exactly one extra (yu==2)
        ol = overlay_bars(self.plot, o1, BONUS1_COLOR)
        self.overlay.add(ol)
        self.legend = make_hist_legend(self.plot, [
            (BASE_COLOR, "All games"),
            (BONUS1_COLOR, "One 100-pt bonus"),
        ])
        self._grow_up(ol, FadeIn(self.legend), run_time=run_time)
        self.wait(0.4)

    @subscene
    def overlay_two(self, run_time=1.0):
        o2 = sd.overlay_by_yahtzee(2)                 # exactly two extra (yu==3)
        ol = overlay_bars(self.plot, o2, BONUS2_COLOR)
        self.overlay.add(ol)
        # add ONLY the new (third) legend row; the first two stay put
        full = make_hist_legend(self.plot, [
            (BASE_COLOR, "All games"),
            (BONUS1_COLOR, "One 100-pt bonus"),
            (BONUS2_COLOR, "Two 100-pt bonuses"),
        ])
        third = full[2]
        self.legend.add(third)
        self._grow_up(ol, FadeIn(third), run_time=run_time)
        self.wait(0.5)

    # ════════════════════════════════════════════════════════════════════════
    # d–h : scorecard + reduced-points bonus system + bonus bar table
    # ════════════════════════════════════════════════════════════════════════
    def _col3_x(self):
        vc = self.card.value_cells[0]
        return (vc.get_right()[0] + self.card.header_rect.get_right()[0]) / 2

    def _card_num(self, text, pos, color):
        m = crisp_text(text, font=FONT, font_size=SCORECARD_FONT_SIZE * 0.8,
                       color=color, weight="BOLD")
        m.move_to(pos)
        m.set_z_index(2)
        return m

    def _setup_bonus_panel(self):
        H = SCORECARD_FONT_SIZE

        def header(t, color):
            return crisp_text(t, font=FONT, font_size=H * 0.95, color=color,
                              weight="BOLD")

        def item(t):
            return crisp_text(t, font=FONT, font_size=H * 0.8, color=BLACK)

        self.h_giant = header("Giant Bonus (4 pts each)", BONUS2_COLOR)
        self.i_giant = [item("Each Extra Yahtzee")]
        self.h_big = header("Big Bonuses (2 pts each)", BASE_COLOR)
        self.i_big = [item("Top Bonus"), item("Large Straight"), item("Yahtzee")]
        self.h_small = header("Small Bonuses (1 pt each)", HL_COLOR)
        self.i_small = [item("3 of a Kind"), item("4 of a Kind"),
                        item("Full House"), item("Small Straight")]

        lines = [self.h_giant, *self.i_giant, self.h_big, *self.i_big,
                 self.h_small, *self.i_small]
        panel = VGroup(*lines).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
        for it in self.i_giant + self.i_big + self.i_small:
            it.shift(RIGHT * 0.45)
        panel.move_to([2.9, 0.0, 0])
        self.bonus_panel = panel
        self.panel_card = self._card_behind(panel, pad=0.5)

    @subscene
    def card_in(self, run_time=1.0):
        self.card = get_scorecard(scores=[None] * 14, center=LEFT_SC,
                                  show_summary=False)
        self.play(FadeOut(self.plot, self.overlay, self.legend),
                  run_time=run_time * 0.5)
        self.plot = self.overlay = self.legend = None
        self.play(FadeIn(self.card, shift=RIGHT * 1.5), run_time=run_time)
        self.wait(0.3)
        self.card.highlight_rows(self, TOP_ROWS, lag_ratio=0.0, run_time=1.2)
        self.wait(0.2)
        self.card.highlight_rows(self, [CHANCE_ROW], run_time=0.8)
        self.wait(0.3)

    @subscene
    def giant_bonus(self, run_time=0.8):
        self._setup_bonus_panel()
        self.card_numbers = VGroup()
        n4 = self._card_num("+4", [self._col3_x(),
                                   self.card.value_cells[YAHTZEE_ROW].get_center()[1], 0],
                            BONUS2_COLOR)
        self.card_numbers.add(n4)
        self.play(FadeIn(self.panel_card), run_time=run_time)
        self.play(FadeIn(self.h_giant, shift=RIGHT * 0.2), run_time=run_time)
        self.play(FadeIn(self.i_giant[0], shift=RIGHT * 0.2),
                  FadeIn(n4, shift=LEFT * 0.2), run_time=run_time)
        self.wait(0.3)

    @subscene
    def fill_bonuses(self, run_time=0.7):
        vc = self.card.value_cells
        c3 = self._col3_x()
        top_y = (vc[0].get_center()[1] + vc[5].get_center()[1]) / 2

        self.play(FadeIn(self.h_big, shift=RIGHT * 0.2), run_time=run_time)
        big = [
            (self.i_big[0], self._card_num("+2", [c3, top_y, 0], BASE_COLOR)),
            (self.i_big[1], self._card_num("+2", vc[10].get_center(), BASE_COLOR)),
            (self.i_big[2], self._card_num("+2", vc[11].get_center(), BASE_COLOR)),
        ]
        for it, num in big:
            self.card_numbers.add(num)
            self.play(FadeIn(it, shift=RIGHT * 0.2), FadeIn(num, shift=LEFT * 0.2),
                      run_time=run_time)
        self.wait(0.2)

        self.play(FadeIn(self.h_small, shift=RIGHT * 0.2), run_time=run_time)
        small = [
            (self.i_small[0], self._card_num("+1", vc[6].get_center(), HL_COLOR)),
            (self.i_small[1], self._card_num("+1", vc[7].get_center(), HL_COLOR)),
            (self.i_small[2], self._card_num("+1", vc[8].get_center(), HL_COLOR)),
            (self.i_small[3], self._card_num("+1", vc[9].get_center(), HL_COLOR)),
        ]
        for it, num in small:
            self.card_numbers.add(num)
            self.play(FadeIn(it, shift=RIGHT * 0.2), FadeIn(num, shift=LEFT * 0.2),
                      run_time=run_time)
        self.wait(0.4)

    @subscene
    def bonus_table(self, run_time=1.5):
        self.play(FadeOut(self.bonus_panel, self.panel_card), run_time=run_time * 0.4)
        self.bonus_panel = self.panel_card = None

        self.table_rows = sd.bonus_table_rows()
        self.table = get_bar_graph(self.table_rows, bar_max_width=3.6,
                                   short_color=BASE_COLOR, long_color=GREY)
        self.table.scale(1.05)
        self.table_card = self._card_behind(self.table, pad=0.45)
        VGroup(self.table, self.table_card).move_to([2.9, 0, 0])
        self.play(FadeIn(self.table_card), FadeIn(self.table, shift=RIGHT * 0.3),
                  run_time=run_time)
        self.wait(0.4)
        self._emph([YAHTZEE_ROW], [6])                 # yahtzee box + table row
        self._emph([9, 10], [4, 5])                    # small & large straight
        self.wait(0.2)

    @subscene
    def highlight_kinds(self, run_time=0.9):
        self._emph([6, 7], [1, 2])                     # 3- & 4-of-a-kind
        self.wait(0.3)

    def _emph(self, card_rows, table_idxs, hold=1.5, run_time=0.6):
        """Hold a scorecard-box highlight (stays up for ``hold`` s) while the
        matching bar-graph label + % go bold. Uses overlaid copies, so nothing on
        the card or table is mutated — a clean FadeOut restores everything."""
        extras = VGroup()
        ins = []
        for r in card_rows:
            fill, border, bold = self.card._row_highlight(r, YELLOW, 0.45)
            extras.add(fill, border, bold)
            ins += [FadeIn(fill), FadeIn(border), FadeIn(bold)]
        for i in table_idxs:
            lab, pct = self.table[i][0], self.table[i][3]
            blab = crisp_text(self.table_rows[i]["label"], font=FONT,
                              font_size=FONT_SIZE_SM * 1.05, color=BLACK,
                              weight="BOLD").move_to(lab, aligned_edge=RIGHT)
            bpct = crisp_text(f"{self.table_rows[i]['pct']:.0f}%", font=FONT,
                              font_size=FONT_SIZE_SM * 1.05, color=BLACK,
                              weight="BOLD").move_to(pct, aligned_edge=LEFT)
            blab.set_z_index(5)
            bpct.set_z_index(5)
            extras.add(blab, bpct)
            ins += [FadeIn(blab), FadeIn(bpct)]
        self.play(*ins, run_time=run_time)
        self.wait(hold)
        self.play(FadeOut(extras), run_time=run_time)

    # ════════════════════════════════════════════════════════════════════════
    # i–q : back to the plot, highlight peak regions by reduced-bonus points
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def plot_back(self, run_time=1.0):
        self.plot = self._build_plot()
        self.play(FadeOut(self.card, self.card_numbers, self.table, self.table_card),
                  run_time=run_time * 0.5)
        self.card = self.card_numbers = self.table = self.table_card = None
        self.cur_overlay = None
        self.legend = None
        rest = VGroup(*[m for m in self.plot.submobjects if m is not self.plot.bars])
        self._grow_up(self.plot.bars, FadeIn(rest), run_time=run_time)
        self.wait(0.3)

    def _highlight(self, counts, label, color, run_time, first=False):
        """First call grows the overlay up; later calls Transform from the current
        overlay to the new one. Both are FULL-GRID layers (a bar per score), so the
        Transform changes each bar's HEIGHT in place (some grow, some shrink)."""
        new_ol = overlay_bars(self.plot, counts, color, full_grid=True)
        new_leg = make_hist_legend(self.plot, [
            (BASE_COLOR, "All games"), (color, label)])
        if first or self.cur_overlay is None:
            self.cur_overlay = new_ol
            self.legend = new_leg
            self._grow_up(new_ol, FadeIn(new_leg), run_time=run_time)
        else:
            self.play(Transform(self.cur_overlay, new_ol),
                      Transform(self.legend, new_leg), run_time=run_time)
        self.wait(0.4)

    @subscene
    def right_bumps(self, run_time=1.0):
        self._highlight(sd.overlay_yahtzee_bumps(), "Extra yahtzees",
                        HL_COLOR, run_time, first=True)

    @subscene
    def all_big(self, run_time=1.0):
        self._highlight(sd.overlay_all_big_bonuses(), "All big bonuses",
                        HL_COLOR, run_time)

    @subscene
    def all_bonuses(self, run_time=1.0):
        self._highlight(sd.overlay_by_reduced(10), "All regular bonuses (10 points)",
                        HL_COLOR, run_time)

    @subscene
    def minus_one_small(self, run_time=1.0):
        self._highlight(sd.overlay_by_reduced(9), "Missing one small (9)",
                        HL_COLOR, run_time)

    @subscene
    def minus_two_three(self, run_time=1.0):
        self._highlight(sd.overlay_by_reduced(8), "Missing 2 pts", HL_COLOR, run_time)
        self._highlight(sd.overlay_by_reduced(7), "Missing 3 pts", HL_COLOR, run_time)

    @subscene
    def minus_four(self, run_time=1.0):
        self._highlight(sd.overlay_by_reduced(6), "Missing 4 pts", HL_COLOR, run_time)

    @subscene
    def minus_five(self, run_time=1.0):
        self._highlight(sd.overlay_by_reduced(5), "Missing 5 pts", HL_COLOR, run_time)

    @subscene
    def below_five(self, run_time=1.0):
        self._highlight(sd.overlay_reduced_below(5), "Missing 6+ pts",
                        HL_COLOR, run_time)
        self.play(FadeOut(self.plot, self.cur_overlay, self.legend), run_time=0.8)
        self.plot = self.cur_overlay = self.legend = None
