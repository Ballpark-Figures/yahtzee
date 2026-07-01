from pathlib import Path
import sys

import numpy as np

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
Y_MAX_PCT  = 1.85         # FIXED percent scale (so 1% stays 1%); ~= tallest peak
X_TICK_STEP = 50

BASE_COLOR = ACCENT_FILL   # bars
MED_COLOR  = ACCENT_GOLD   # median-bar highlight

BOX_TOP     = PLOT_C[1] + PLOT_H / 2
TITLE_Y     = BOX_TOP + 0.85
MED_LABEL_Y = BOX_TOP + 0.32

# each histogram = best of N opponents (max of N scores); N=1 is the single plot
SERIES = [1, 2, 3, 5]


class Multiplayer(YahtzeeScene):
    def setup_scene(self):
        pass

    # ── one shared coordinate system: fixed score→x scale + union domain, and a
    #    per-histogram window centre so the camera pans right as N grows ────────
    def _prepare(self):
        self.dists = {n: (sd.score_distribution() if n == 1
                          else sd.maxN_distribution(n)) for n in SERIES}
        ranges = {n: trimmed_range(self.dists[n], MIN_PROB) for n in self.dists}
        self.union = (min(lo for lo, _ in ranges.values()),
                      max(hi for _, hi in ranges.values()))
        span = max(hi - lo for lo, hi in ranges.values())   # widest fills the box
        self.scale_x = PLOT_W / span
        self.centers = {n: (lo + hi) / 2 for n, (lo, hi) in ranges.items()}

    def _build(self, n):
        """The bars/axes/ticks + median MARKER (no text — the scene owns the
        median label + the title so their numbers can be live counters)."""
        return get_panning_histogram(
            self.dists[n], self.centers[n], self.union[0], self.union[1],
            self.scale_x, Y_MAX_PCT, center=PLOT_C, width=PLOT_W, height=PLOT_H,
            bar_color=BASE_COLOR, x_tick_step=X_TICK_STEP,
            y_axis_label="Frequency (%)", x_axis_label="Score", title=None,
            median=sd.maxN_median(n), median_color=MED_COLOR, median_text=False,
        )

    # ── scene-owned text (numbers are driven by counters, not crossfades) ─────
    def _med_x(self, med_val, center_val):
        return PLOT_C[0] + (med_val - center_val) * self.scale_x

    def _plain_title(self, text):
        m = crisp_text(text, font=FONT, font_size=FONT_SIZE_LG, color=BLACK)
        m.move_to([PLOT_C[0], TITLE_Y, 0])
        return m

    def _count_title(self, n):
        row = VGroup(
            crisp_text("Best of", font=FONT, font_size=FONT_SIZE_LG, color=BLACK),
            crisp_text(str(n), font=FONT, font_size=FONT_SIZE_LG, color=BLACK),
            crisp_text("opponents", font=FONT, font_size=FONT_SIZE_LG, color=BLACK),
        ).arrange(RIGHT, buff=0.22)
        row.move_to([PLOT_C[0], TITLE_Y, 0])
        return row

    def _med_label(self, med, x):
        row = VGroup(
            crisp_text("Median", font=FONT, font_size=FONT_SIZE_SM, color=BLACK,
                       weight="BOLD"),
            crisp_text(str(med), font=FONT, font_size=FONT_SIZE_SM, color=BLACK,
                       weight="BOLD"),
        ).arrange(RIGHT, buff=0.14)
        row.move_to([x, MED_LABEL_Y, 0])
        return row

    def _grow_up(self, bars, *extra, run_time=1.0):
        for b in bars:
            b.save_state()
            b.stretch(1e-3, dim=1, about_edge=DOWN)
        self.play(*[Restore(b) for b in bars], *extra, run_time=run_time)

    def _transition(self, n, count_title, run_time):
        """Morph+pan the plot to best-of-``n`` while COUNTING the median (linear)
        and — when ``count_title`` — the title's N (log scale). The first step
        instead crossfades the title ("Score Frequencies" → "Best of 2 …")."""
        prev_n = self.cur_n
        new = self._build(n)
        c0, c1 = self.centers[prev_n], self.centers[n]
        m0, m1 = self.cur_median, sd.maxN_median(n)

        ct, mt = ValueTracker(c0), ValueTracker(m0)
        self.median_label.add_updater(lambda mob: mob.become(
            self._med_label(round(mt.get_value()),
                            self._med_x(mt.get_value(), ct.get_value()))))

        anims = morph_panning(self.plot, new)
        anims += [ct.animate.set_value(c1), mt.animate.set_value(m1)]

        if count_title:
            nt = ValueTracker(np.log(prev_n))
            self.title.add_updater(lambda mob: mob.become(
                self._count_title(int(round(np.exp(nt.get_value()))))))
            anims.append(nt.animate.set_value(np.log(n)))
            self.play(*anims, run_time=run_time)
            self.title.clear_updaters()
            self.title.become(self._count_title(n))
        else:
            new_title = self._count_title(n)
            anims += [FadeOut(self.title), FadeIn(new_title)]
            self.play(*anims, run_time=run_time)
            self.title = new_title

        self.median_label.clear_updaters()
        self.median_label.become(self._med_label(m1, self._med_x(m1, c1)))
        self.cur_n, self.cur_median, self.plot = n, m1, new

    # ════════════════════════════════════════════════════════════════════════
    # a : single-player plot, thick median marker + label above the bars
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def show_single(self, run_time=1.5):
        self._prepare()
        self.cur_n = SERIES[0]
        self.cur_median = sd.maxN_median(self.cur_n)
        self.plot = self._build(self.cur_n)
        self.title = self._plain_title("Score Frequencies")
        self.median_label = self._med_label(
            self.cur_median, self._med_x(self.cur_median, self.centers[self.cur_n]))
        med_hl, med_leader = self.plot.median_group
        rest = VGroup(self.plot.x_axis, self.plot.y_axis, self.plot.y_ticks,
                      self.plot.x_ticks, self.plot.axis_labels)
        self._grow_up([*self.plot.bars, med_hl], FadeIn(rest), FadeIn(med_leader),
                      FadeIn(self.title), FadeIn(self.median_label),
                      run_time=run_time)
        self.wait(0.5)

    # ════════════════════════════════════════════════════════════════════════
    # b–d : best-of-N — morph+pan, median counts up, title N counts on log scale
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def best_of_2(self, run_time=2.0):
        self._transition(2, count_title=False, run_time=run_time)   # title crossfade
        self.wait(0.5)

    @subscene
    def best_of_3(self, run_time=2.0):
        self._transition(3, count_title=True, run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_5(self, run_time=2.0):
        self._transition(5, count_title=True, run_time=run_time)
        self.wait(0.5)
