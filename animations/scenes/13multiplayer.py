from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from bpkfigures.style import ACCENT_FILL, ACCENT_GOLD
from bpkfigures.histogram import get_histogram, morph_histogram
from assets import score_data as sd

# ── plot geometry / look (knobs for the user) — matches scene 07's plot ───────
PLOT_C    = ORIGIN
PLOT_W    = 8.0
PLOT_H    = 4.0
MIN_PROB  = 1e-4

BASE_COLOR = ACCENT_FILL   # bars
MED_COLOR  = ACCENT_GOLD   # median-bar highlight


class Multiplayer(YahtzeeScene):
    def setup_scene(self):
        pass

    # ── shared builder: one histogram for a {score: prob} distribution ───────
    def _build_plot(self, counts, title, median):
        return get_histogram(
            None, counts=counts, min_prob=MIN_PROB,
            center=PLOT_C, width=PLOT_W, height=PLOT_H,
            bar_color=BASE_COLOR, bar_ratio=1.05, x_tick_step=50,
            show_y_axis=True, y_axis_label="Frequency (%)",
            x_axis_label="Score", title=title,
            median=median, median_color=MED_COLOR,
        )

    def _grow_up(self, bars, *extra, run_time=1.0):
        """Height-only grow: each bar rises from the axis (x fixed). ``extra``
        animations play alongside."""
        for b in bars:
            b.save_state()
            b.stretch(1e-3, dim=1, about_edge=DOWN)
        self.play(*[Restore(b) for b in bars], *extra, run_time=run_time)

    def _morph_to(self, counts, title, median, run_time):
        """Smoothly reshape the current plot into a new distribution."""
        new = self._build_plot(counts, title, median)
        self.play(*morph_histogram(self.plot, new), run_time=run_time)
        self.plot = new

    # ════════════════════════════════════════════════════════════════════════
    # a : the single-player plot from scene 07, with the median highlighted
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def show_single(self, run_time=1.5):
        self.plot = self._build_plot(
            sd.score_distribution(), "Score Frequencies", sd.maxN_median(1))
        med_hl, med_lab = self.plot.median_group
        rest = VGroup(*[m for m in self.plot.submobjects
                        if m is not self.plot.bars
                        and m is not self.plot.median_group])
        self._grow_up([*self.plot.bars, med_hl],
                      FadeIn(rest), FadeIn(med_lab), run_time=run_time)
        self.wait(0.5)

    # ════════════════════════════════════════════════════════════════════════
    # b–d : best-of-N opponents (max of N scores), median climbing right
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def best_of_2(self, run_time=1.5):
        self._morph_to(sd.maxN_distribution(2), "Best of 2 opponents",
                       sd.maxN_median(2), run_time)
        self.wait(0.5)

    @subscene
    def best_of_3(self, run_time=1.5):
        self._morph_to(sd.maxN_distribution(3), "Best of 3 opponents",
                       sd.maxN_median(3), run_time)
        self.wait(0.5)

    @subscene
    def best_of_5(self, run_time=1.5):
        self._morph_to(sd.maxN_distribution(5), "Best of 5 opponents",
                       sd.maxN_median(5), run_time)
        self.wait(0.5)
