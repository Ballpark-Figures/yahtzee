from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from bpkfigures.histogram import get_histogram, overlay_bars, make_hist_legend
from bpkfigures.bar_graph import get_bar_graph
from assets import score_data as sd

# ── plot geometry / look (knobs for the user) ─────────────────────────────────
PLOT_C   = ORIGIN
PLOT_W   = 8.0                # matches the battleship histograms' default width
PLOT_H   = 4.0
MIN_PROB = 1e-4              # auto-trims the score range to where mass lives

BASE_COLOR   = "#3C5A99"     # navy bars / +2 big-bonus numbers
BONUS1_COLOR = ORANGE        # one 100-pt yahtzee bonus
BONUS2_COLOR = RED           # two 100-pt yahtzee bonuses / +4 giant bonus
HL_COLOR     = "#E8A33D"     # peak-highlight colour / +1 small-bonus numbers

# scorecard row indices (0-5 top, 6 3oak,7 4oak,8 FH,9 SS,10 LS,11 Yahtzee,
# 12 Chance). The yahtzee BONUS has no row of its own.
TOP_ROWS   = list(range(6))
CHANCE_ROW = 12
YAHTZEE_ROW = 11


class Histogram(YahtzeeScene):
    # Nothing on screen from frame 0; every subscene builds what it owns.
    def setup_scene(self):
        pass

    # ── shared builders ──────────────────────────────────────────────────────
    def _build_plot(self):
        return get_histogram(
            None, counts=self.base, min_prob=MIN_PROB,
            center=PLOT_C, width=PLOT_W, height=PLOT_H,
            bar_color=BASE_COLOR, bar_ratio=1.0, x_tick_step=50,
            show_y_axis=True, y_axis_label="Frequency (%)",
            x_axis_label="Score", title="Score Frequencies",
        )

    def _grow_in_plot(self, run_time):
        """Bars grow up from the axis while the axes/labels/title fade in."""
        rest = VGroup(*[m for m in self.plot.submobjects
                        if m is not self.plot.bars])
        self.play(GrowFromEdge(self.plot.bars, DOWN), FadeIn(rest),
                  run_time=run_time)

    # ════════════════════════════════════════════════════════════════════════
    # a–c : the histogram and the two yahtzee-bonus overlays
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def show_plot(self, run_time=1.5):
        self.base = sd.score_distribution()
        self.plot = self._build_plot()
        self.overlay = VGroup()
        self.legend = None
        self._grow_in_plot(run_time)
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
        self.play(GrowFromEdge(ol, DOWN), FadeIn(self.legend), run_time=run_time)
        self.wait(0.4)

    @subscene
    def overlay_two(self, run_time=1.0):
        o2 = sd.overlay_by_yahtzee(2)                 # exactly two extra (yu==3)
        ol = overlay_bars(self.plot, o2, BONUS2_COLOR)
        self.overlay.add(ol)
        new_legend = make_hist_legend(self.plot, [
            (BASE_COLOR, "All games"),
            (BONUS1_COLOR, "One 100-pt bonus"),
            (BONUS2_COLOR, "Two 100-pt bonuses"),
        ])
        self.play(GrowFromEdge(ol, DOWN), Transform(self.legend, new_legend),
                  run_time=run_time)
        self.wait(0.5)

    # ════════════════════════════════════════════════════════════════════════
    # d–h : scorecard + the reduced-points bonus system + the bonus bar table
    # ════════════════════════════════════════════════════════════════════════
    def _col3_x(self):
        """x-centre of the scorecard's 3rd (summary) column."""
        vc = self.card.value_cells[0]
        return (vc.get_right()[0] + self.card.header_rect.get_right()[0]) / 2

    def _card_num(self, text, pos, color):
        m = crisp_text(text, font=FONT, font_size=SCORECARD_FONT_SIZE * 0.8,
                       color=color, weight="BOLD")
        m.move_to(pos)
        m.set_z_index(2)
        return m

    def _setup_bonus_panel(self):
        """The right-half text list of the new point system (headers + items),
        built but not shown — subscenes e/f reveal it group by group."""
        H = SCORECARD_FONT_SIZE

        def header(t, color):
            return crisp_text(t, font=FONT, font_size=H * 0.95, color=color,
                              weight="BOLD")

        def item(t):
            return crisp_text(t, font=FONT, font_size=H * 0.8, color=BLACK)

        self.h_giant = header("Giant Bonus (4 pts)", BONUS2_COLOR)
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
            it.shift(RIGHT * 0.45)                    # indent items under headers
        panel.move_to([2.7, 0.0, 0])
        self.bonus_panel = panel

    @subscene
    def card_in(self, run_time=1.0):
        self.card = get_scorecard(scores=[None] * 14, center=LEFT_SC,
                                  show_summary=False)
        self.play(FadeOut(self.plot, self.overlay, self.legend),
                  run_time=run_time * 0.5)
        self.plot = self.overlay = self.legend = None
        self.play(FadeIn(self.card, shift=RIGHT * 1.5), run_time=run_time)
        self.wait(0.3)
        # top section all at once, then chance after
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
        self.play(FadeIn(self.h_giant, shift=RIGHT * 0.2), run_time=run_time)
        self.play(FadeIn(self.i_giant[0], shift=RIGHT * 0.2),
                  FadeIn(n4, shift=LEFT * 0.2), run_time=run_time)
        self.wait(0.3)

    @subscene
    def fill_bonuses(self, run_time=0.7):
        vc = self.card.value_cells
        c3 = self._col3_x()
        top_y = (vc[0].get_center()[1] + vc[5].get_center()[1]) / 2

        # big bonuses (+2): top bonus -> col 3 of top section; LS & Yahtzee -> col 2
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

        # small bonuses (+1): all in col 2
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
        # clear the point-system text list, KEEP the card numbers
        self.play(FadeOut(self.bonus_panel), run_time=run_time * 0.4)
        self.bonus_panel = None

        rows = sd.bonus_table_rows()
        self.table = get_bar_graph(rows, bar_max_width=4.0, short_color=BASE_COLOR)
        self.table.scale(1.1).next_to(self.card, RIGHT, buff=0.55)
        self.play(FadeIn(self.table, shift=RIGHT * 0.3), run_time=run_time)
        self.wait(0.4)
        # highlight the SCORECARD boxes (not the bar graph): yahtzee, then straights
        self.card.highlight_rows(self, [YAHTZEE_ROW], run_time=0.8)
        self.wait(0.2)
        self.card.highlight_rows(self, [9, 10], run_time=0.9)   # small & large straight
        self.wait(0.4)

    @subscene
    def highlight_kinds(self, run_time=0.9):
        self.card.highlight_rows(self, [6, 7], run_time=run_time)   # 3- & 4-of-a-kind
        self.wait(0.4)

    # ════════════════════════════════════════════════════════════════════════
    # i–q : back to the plot, highlight peak regions by reduced-bonus points
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def plot_back(self, run_time=1.0):
        self.plot = self._build_plot()
        self.play(FadeOut(self.card, self.card_numbers, self.table),
                  run_time=run_time * 0.5)
        self.card = self.card_numbers = self.table = None
        self.cur_overlay = None
        self.legend = None
        self._grow_in_plot(run_time)
        self.wait(0.3)

    def _highlight(self, counts, label, color, run_time, first=False):
        """First call grows the overlay in; later calls Transform from the current
        overlay (and legend) to the new one — the morph the user liked."""
        new_ol = overlay_bars(self.plot, counts, color)
        new_leg = make_hist_legend(self.plot, [
            (BASE_COLOR, "All games"), (color, label)])
        if first or self.cur_overlay is None:
            self.cur_overlay = new_ol
            self.legend = new_leg
            self.play(GrowFromEdge(new_ol, DOWN), FadeIn(new_leg), run_time=run_time)
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
