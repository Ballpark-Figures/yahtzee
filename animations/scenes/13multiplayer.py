from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from bpkfigures.style import ACCENT_FILL, ACCENT_GOLD
from bpkfigures.histogram import (get_panning_histogram, morph_panning,
                                  trimmed_range)
from assets import score_data as sd

# ── plot geometry / look (knobs for the user) ─────────────────────────────────
PLOT_C     = ORIGIN
PLOT_W     = 8.0
PLOT_H     = 4.0
MIN_PROB   = 1e-4
Y_MAX_PCT  = 1.9          # FIXED percent scale (so 1% stays 1% across histograms)
X_TICK_STEP = 50

BASE_COLOR = ACCENT_FILL   # bars
MED_COLOR  = ACCENT_GOLD   # median-bar highlight

# each histogram = best of N opponents (max of N scores); N=1 is the single plot
SERIES = [
    (1, "Score Frequencies"),
    (2, "Best of 2 opponents"),
    (3, "Best of 3 opponents"),
    (5, "Best of 5 opponents"),
]


class Multiplayer(YahtzeeScene):
    def setup_scene(self):
        pass

    # ── one shared coordinate system: fixed score→x scale + union domain, and a
    #    per-histogram window centre so the camera pans right as N grows ────────
    def _prepare(self):
        self.dists = {n: (sd.score_distribution() if n == 1
                          else sd.maxN_distribution(n)) for n, _ in SERIES}
        ranges = {n: trimmed_range(self.dists[n], MIN_PROB) for n in self.dists}
        self.union = (min(lo for lo, _ in ranges.values()),
                      max(hi for _, hi in ranges.values()))
        span = max(hi - lo for lo, hi in ranges.values())   # widest fills the box
        self.scale_x = PLOT_W / span
        self.centers = {n: (lo + hi) / 2 for n, (lo, hi) in ranges.items()}

    def _build(self, n, title):
        return get_panning_histogram(
            self.dists[n], self.centers[n], self.union[0], self.union[1],
            self.scale_x, Y_MAX_PCT, center=PLOT_C, width=PLOT_W, height=PLOT_H,
            bar_color=BASE_COLOR, x_tick_step=X_TICK_STEP,
            y_axis_label="Frequency (%)", x_axis_label="Score", title=title,
            median=sd.maxN_median(n), median_color=MED_COLOR,
        )

    def _grow_up(self, bars, *extra, run_time=1.0):
        """Height-only grow: each bar rises from the axis. ``extra`` plays along."""
        for b in bars:
            b.save_state()
            b.stretch(1e-3, dim=1, about_edge=DOWN)
        self.play(*[Restore(b) for b in bars], *extra, run_time=run_time)

    def _morph_to(self, n, title, run_time):
        new = self._build(n, title)
        self.play(*morph_panning(self.plot, new), run_time=run_time)
        self.plot = new

    # ════════════════════════════════════════════════════════════════════════
    # a : single-player plot, median highlighted (label above the bars)
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def show_single(self, run_time=1.5):
        self._prepare()
        self.plot = self._build(*SERIES[0])
        med_hl, med_leader, med_lab = self.plot.median_group
        rest = VGroup(self.plot.x_axis, self.plot.y_axis, self.plot.y_ticks,
                      self.plot.x_ticks, self.plot.axis_labels,
                      self.plot.title_text)
        self._grow_up([*self.plot.bars, med_hl], FadeIn(rest),
                      FadeIn(med_leader), FadeIn(med_lab), run_time=run_time)
        self.wait(0.5)

    # ════════════════════════════════════════════════════════════════════════
    # b–d : best-of-N — bars morph in place while the field pans right, median climbs
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def best_of_2(self, run_time=2.0):
        self._morph_to(*SERIES[1], run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_3(self, run_time=2.0):
        self._morph_to(*SERIES[2], run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_5(self, run_time=2.0):
        self._morph_to(*SERIES[3], run_time=run_time)
        self.wait(0.5)
