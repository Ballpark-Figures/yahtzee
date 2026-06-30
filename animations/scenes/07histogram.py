from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from bpkfigures.histogram import get_histogram
from bpkfigures.bar_graph import get_bar_graph
from assets import score_data as sd

# ── plot geometry / look (rough — knobs for the user) ─────────────────────────
PLOT_C   = ORIGIN
PLOT_W   = 11.0
PLOT_H   = 4.3
MIN_PROB = 1e-4               # auto-trims the score range to where mass lives

BASE_COLOR = "#3C5A99"        # navy bars
BONUS1_COLOR = ORANGE         # one 100-pt yahtzee bonus
BONUS2_COLOR = RED            # two 100-pt yahtzee bonuses
HL_COLOR   = "#E8A33D"        # peak-highlight colour (reduced-point beats)

# scorecard row indices (0-5 top, 6 3oak,7 4oak,8 FH,9 SS,10 LS,11 Yahtzee,
# 12 Chance, 13 Yahtzee bonus)
TOP_ROWS   = list(range(6))
CHANCE_ROW = 12
YBONUS_ROW = 13
BIG_ROWS   = [10, 11]         # large straight, yahtzee (top bonus handled apart)
SMALL_ROWS = [6, 7, 8, 9]     # 3oak, 4oak, full house, small straight


class Histogram(YahtzeeScene):
    # Nothing is on screen from frame 0; every subscene builds what it owns.
    def setup_scene(self):
        pass

    # ── shared builders ──────────────────────────────────────────────────────
    def _build_plot(self, overlays=None):
        """A fresh score histogram. Base counts/max_mag/range are identical every
        call (same `counts`, same `min_prob`), so variants line up for Transform;
        overlays just add coloured bars on top and dim the base."""
        return get_histogram(
            None, counts=self.base, min_prob=MIN_PROB,
            center=PLOT_C, width=PLOT_W, height=PLOT_H,
            bar_color=BASE_COLOR, x_tick_step=50,
            show_y_axis=True, y_axis_label="Frequency (%)",
            base_label=("All games" if overlays else None),
            overlays=overlays,
        )

    # ════════════════════════════════════════════════════════════════════════
    # a–c : the histogram and the two yahtzee-bonus overlays
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def show_plot(self, run_time=1.2):
        self.base = sd.score_distribution()
        self.plot = self._build_plot()
        self.play(FadeIn(self.plot), run_time=run_time)
        self.wait(0.4)

    def _swap_plot(self, new, run_time):
        """Cross-fade to a new plot variant. The base bars are identical across
        variants, so this reads as the overlay lighting up — and it renders far
        faster than a Transform over ~400 bars."""
        self.play(FadeOut(self.plot), FadeIn(new), run_time=run_time)
        self.plot = new

    @subscene
    def overlay_one(self, run_time=1.0):
        o1 = sd.overlay_by_yahtzee(1)
        new = self._build_plot([(o1, BONUS1_COLOR, "One 100-pt bonus")])
        self._swap_plot(new, run_time)
        self.wait(0.4)

    @subscene
    def overlay_two(self, run_time=1.0):
        o1 = sd.overlay_by_yahtzee(1)
        o2 = sd.overlay_by_yahtzee(2)
        new = self._build_plot([
            (o1, BONUS1_COLOR, "One 100-pt bonus"),
            (o2, BONUS2_COLOR, "Two 100-pt bonuses"),
        ])
        self._swap_plot(new, run_time)
        self.wait(0.5)

    # ════════════════════════════════════════════════════════════════════════
    # d–h : scorecard + the reduced-points bonus system + the bonus bar table
    #       (column-3 point labels are ROUGH placeholders — layout is a knob)
    # ════════════════════════════════════════════════════════════════════════
    def _point_label(self, row, txt, color):
        cell = self.card.value_cells[row]
        lab = crisp_text(txt, font=FONT, font_size=SCORECARD_FONT_SIZE * 0.8,
                         color=color, weight="BOLD")
        lab.next_to(cell, RIGHT, buff=0.35)
        return lab

    @subscene
    def card_in(self, run_time=1.0):
        # remove the plot, bring the scorecard in on the left
        self.card = get_scorecard(scores=[None] * 14, center=LEFT_SC,
                                  show_summary=False)
        self.play(FadeOut(self.plot), run_time=run_time * 0.5)
        self.plot = None                      # consumed; rebuilt in `plot_back`
        self.play(FadeIn(self.card, shift=RIGHT * 1.5), run_time=run_time)
        self.wait(0.3)
        # highlight top section + chance (unlikely to make or break the game)
        self.card.highlight_rows(self, TOP_ROWS + [CHANCE_ROW],
                                 lag_ratio=0.15, run_time=2.0)
        self.wait(0.3)

    @subscene
    def giant_bonus(self, run_time=0.8):
        # the 100-pt yahtzee bonus → its own category, worth 4 points. It has no
        # labelled row on the card, so the "+4" sits at the top of the right
        # column. (ROUGH placement — a knob.)
        self.card.highlight_rows(self, [11], run_time=0.8)        # yahtzee row
        self.ybonus_lbl = crisp_text("+4", font=FONT,
                                     font_size=SCORECARD_FONT_SIZE * 0.9,
                                     color=BONUS2_COLOR, weight="BOLD")
        self.ybonus_lbl.next_to(self.card.get_corner(UR), DL, buff=0.3)
        self.play(FadeIn(self.ybonus_lbl, shift=DOWN * 0.2), run_time=run_time)
        self.wait(0.4)

    @subscene
    def fill_bonuses(self, run_time=0.6):
        # big bonuses (+2): top bonus, large straight, yahtzee
        self.big_lbls = VGroup(*[self._point_label(r, "+2", BASE_COLOR)
                                 for r in BIG_ROWS])
        # top-section bonus has no row of its own — tag it near the top section
        top_lbl = crisp_text("+2", font=FONT,
                             font_size=SCORECARD_FONT_SIZE * 0.8,
                             color=BASE_COLOR, weight="BOLD")
        top_lbl.next_to(self.card.value_cells[5], RIGHT, buff=0.35)
        self.big_lbls.add(top_lbl)
        self.play(LaggedStart(*[FadeIn(m, shift=LEFT * 0.2) for m in self.big_lbls],
                              lag_ratio=0.3), run_time=run_time * 3)
        self.wait(0.3)
        # small bonuses (+1): 3oak, 4oak, full house, small straight
        self.small_lbls = VGroup(*[self._point_label(r, "+1", HL_COLOR)
                                   for r in SMALL_ROWS])
        self.play(LaggedStart(*[FadeIn(m, shift=LEFT * 0.2) for m in self.small_lbls],
                              lag_ratio=0.3), run_time=run_time * 3)
        self.wait(0.4)
        # clear the point system before the table beat
        self.play(FadeOut(self.ybonus_lbl, self.big_lbls, self.small_lbls),
                  run_time=run_time)
        self.ybonus_lbl = self.big_lbls = self.small_lbls = None

    @subscene
    def bonus_table(self, run_time=1.5):
        rows = sd.bonus_table_rows()
        self.table = get_bar_graph(rows, bar_max_width=3.6, short_color=BASE_COLOR)
        self.table.scale(0.85).next_to(self.card, RIGHT, buff=0.8)
        self.play(FadeIn(self.table, shift=RIGHT * 0.3), run_time=run_time)
        self.wait(0.4)
        # highlight yahtzee (row 6 in the table), then the straights (rows 4,5)
        self.play(Indicate(self.table[6], color=BONUS2_COLOR, scale_factor=1.05),
                  run_time=0.8)
        self.wait(0.2)
        self.play(Indicate(self.table[4], color=HL_COLOR, scale_factor=1.05),
                  Indicate(self.table[5], color=HL_COLOR, scale_factor=1.05),
                  run_time=0.8)
        self.wait(0.4)

    @subscene
    def highlight_kinds(self, run_time=0.8):
        # 3- and 4-of-a-kind give surprisingly few points (the fading bars)
        self.play(Indicate(self.table[1], color=HL_COLOR, scale_factor=1.05),
                  Indicate(self.table[2], color=HL_COLOR, scale_factor=1.05),
                  run_time=run_time)
        self.wait(0.4)

    # ════════════════════════════════════════════════════════════════════════
    # i–q : back to the plot, highlight peak regions by reduced-bonus points
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def plot_back(self, run_time=1.0):
        self.plot = self._build_plot()
        self.play(FadeOut(self.card, self.table), run_time=run_time * 0.5)
        self.card = self.table = None
        self.play(FadeIn(self.plot), run_time=run_time)
        self.wait(0.3)

    def _highlight(self, overlay_counts, label, color, run_time):
        new = self._build_plot([(overlay_counts, color, label)])
        self._swap_plot(new, run_time)
        self.wait(0.4)

    @subscene
    def right_bumps(self, run_time=1.0):
        self._highlight(sd.overlay_yahtzee_bumps(), "Extra yahtzees",
                        BONUS2_COLOR, run_time)

    @subscene
    def all_big(self, run_time=1.0):
        # games that got all three big bonuses (top, large straight, yahtzee)
        self._highlight(sd.overlay_by_reduced(10), "All regular bonuses",
                        HL_COLOR, run_time)

    @subscene
    def all_bonuses(self, run_time=1.0):
        self._highlight(sd.overlay_by_reduced(10), "All bonuses (10 pts)",
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
        self.play(FadeOut(self.plot), run_time=0.8)
        self.plot = None
