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
X_TICK_STEP = 50
# y-axis rescales per histogram so the tallest bar fills this fraction of the box;
# y-ticks are value-keyed, so "1%" slides to its new height and "1.5%" fades in.
Y_HEADROOM = 0.9
# candidate % ticks across ALL scales (flat ~1% up to the perfect-game ~50%
# spike). The histogram picks a nice step per plot and fades the rest, so the
# grid just has to contain every value any step might land on.
Y_TICKS = (0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50)
TITLE_MAXW = 11.0          # scale the counting title down if it would overrun this
NUM_MAXW   = 12.0          # width cap for the finale number on its own line
STACK_MID  = 3.0           # finale: y of the number line in the stacked title
STACK_GAP  = 0.72          # finale: gap from the number line to "Best of"/"opponents"

BASE_COLOR = ACCENT_FILL   # bars
MED_COLOR  = ACCENT_GOLD   # median-bar highlight

BOX_TOP  = PLOT_C[1] + PLOT_H / 2
TITLE_Y  = BOX_TOP + 0.85
# median callout: leader rises to a "shelf" just above the peak, then runs right
# to a label parked in the empty upper-right of the plot
SHELF_Y    = BOX_TOP - 0.2
MED_ANCHOR = [PLOT_C[0] + PLOT_W * 0.20, SHELF_Y, 0]

# each histogram = best of N opponents (max of N scores); N=1 is the single plot.
# Values follow the script's beats (10, then the population beats 79/5000/1M/8.3B);
# the perfect-game count is deferred (not computed yet).
SERIES = [1, 2, 3, 5, 10, 79, 5000, 1_000_000, 8_300_000_000]


class Multiplayer(YahtzeeScene):
    def setup_scene(self):
        pass

    # ── one shared coordinate system: fixed score→x scale + union domain, and a
    #    per-histogram window centre so the camera pans right as N grows ────────
    def _prepare(self):
        # the finale: fewest opponents for which a perfect game is more likely
        # than not (median hits 1575). Computed, not hard-coded.
        self.n_perfect = sd.opponents_for_perfect()
        # (N, median) at each multiple of 10 the median crosses — intermediate
        # checkpoints the beat-to-beat animations morph THROUGH.
        self.checkpoints = sd.median_checkpoints(10)
        self.series = SERIES + [self.n_perfect]
        self.dists = {n: (sd.score_distribution() if n == 1
                          else sd.maxN_distribution(n)) for n in self.series}
        ranges = {n: trimmed_range(self.dists[n], MIN_PROB) for n in self.dists}
        # union/scale from the MAIN beats already span the whole score range, so
        # every in-between checkpoint fits; their dists/centers are built lazily.
        self.union = (min(lo for lo, _ in ranges.values()),
                      max(hi for _, hi in ranges.values()))
        span = max(hi - lo for lo, hi in ranges.values())   # widest fills the box
        self.scale_x = PLOT_W / span
        self.centers = {n: (lo + hi) / 2 for n, (lo, hi) in ranges.items()}

    def _dist(self, n):
        if n not in self.dists:
            self.dists[n] = sd.maxN_distribution(n)
        return self.dists[n]

    def _center(self, n):
        if n not in self.centers:
            lo, hi = trimmed_range(self._dist(n), MIN_PROB)
            self.centers[n] = (lo + hi) / 2
        return self.centers[n]

    def _build(self, n):
        """The bars/axes/ticks + median MARKER (no text — the scene owns the
        median label + the title so their numbers can be live counters)."""
        return get_panning_histogram(
            self._dist(n), self._center(n), self.union[0], self.union[1],
            self.scale_x, center=PLOT_C, width=PLOT_W, height=PLOT_H,
            bar_color=BASE_COLOR, x_tick_step=X_TICK_STEP, y_headroom=Y_HEADROOM,
            y_tick_values=Y_TICKS,
            y_axis_label="Frequency (%)", x_axis_label="Score", title=None,
            median=sd.maxN_median(n), median_color=MED_COLOR,
            median_label_anchor=MED_ANCHOR,
        )

    # ── scene-owned text (numbers are driven by counters, not crossfades) ─────
    def _plain_title(self, text):
        m = crisp_text(text, font=FONT, font_size=FONT_SIZE_LG, color=BLACK)
        m.move_to([PLOT_C[0], TITLE_Y, 0])
        return m

    def _count_title(self, n):
        # one string (not arranged pieces) so the baseline is consistent; the
        # counter rebuilds it each frame anyway
        # Plain Text (not crisp_text): crisp_text supersamples to a huge font that
        # Pango WRAPS for long strings, so the width can't be measured. A plain
        # Text stays one line; scale it down so big-N titles fit.
        m = Text(f"Best of {n:,} opponents", font=FONT, font_size=FONT_SIZE_LG,
                 color=BLACK)
        if m.width > TITLE_MAXW:
            m.scale(TITLE_MAXW / m.width)
        m.move_to([PLOT_C[0], TITLE_Y, 0])
        return m

    def _fit_number(self, n):
        """The finale's opponent count on its own line, scaled to fit."""
        m = Text(f"{n:,}", font=FONT, font_size=FONT_SIZE_LG, color=BLACK)
        if m.width > NUM_MAXW:
            m.scale(NUM_MAXW / m.width)
        return m

    def _med_label(self, med):
        """The "Median NNN" label, left-aligned just right of the callout anchor
        (fixed upper-right of the plot); only its number counts."""
        m = crisp_text(f"Median {med}", font=FONT, font_size=FONT_SIZE_SM,
                       color=BLACK, weight="BOLD")
        m.move_to([MED_ANCHOR[0] + 0.12, MED_ANCHOR[1], 0], aligned_edge=LEFT)
        return m

    def _grow_up(self, bars, *extra, run_time=1.0):
        for b in bars:
            b.save_state()
            b.stretch(1e-3, dim=1, about_edge=DOWN)
        self.play(*[Restore(b) for b in bars], *extra, run_time=run_time)

    def _transition(self, n, count_title, run_time=3.0):
        """One ``run_time``-second beat-to-beat animation that morphs THROUGH the
        intermediate checkpoints (real best-of-N distributions whose median crosses
        each multiple of 10). Each sub-morph gets time proportional to its median-
        delta, so the median rises at a CONSTANT rate over the whole beat. The
        title's N is median-paced (it reaches each checkpoint's N as the median
        passes it). The very first step also crossfades the title structure."""
        prev_n, m0, m1 = self.cur_n, self.cur_median, sd.maxN_median(n)
        inter = [c[0] for c in self.checkpoints
                 if prev_n < c[0] < n and m0 < c[1] < m1]
        seq = [prev_n, *inter, n]                       # N values to morph through
        meds = [m0, *[sd.maxN_median(c) for c in inter], m1]
        total = m1 - m0

        for i in range(len(seq) - 1):
            na, nb, ma, mb = seq[i], seq[i + 1], meds[i], meds[i + 1]
            new = self._build(nb)
            rt = run_time * (mb - ma) / total if total else run_time

            mt = ValueTracker(ma)
            self.median_label.add_updater(
                lambda mob, mt=mt: mob.become(self._med_label(round(mt.get_value()))))
            anims = morph_panning(self.plot, new)
            for a in anims:
                a.rate_func = linear                    # linear so the pan is even across steps
            anims.append(mt.animate(rate_func=linear).set_value(mb))

            if count_title:
                nt = ValueTracker(np.log(float(na)))
                self.title.add_updater(lambda mob, nt=nt: mob.become(
                    self._count_title(int(round(np.exp(nt.get_value()))))))
                anims.append(nt.animate(rate_func=linear).set_value(np.log(float(nb))))
                self.play(*anims, run_time=rt)
                self.title.clear_updaters()
            else:
                new_title = self._count_title(nb)       # 1->2: crossfade structure
                anims += [FadeOut(self.title), FadeIn(new_title)]
                self.play(*anims, run_time=rt)
                self.title = new_title
                count_title = True

            self.median_label.clear_updaters()
            self.plot = new

        self.median_label.become(self._med_label(m1))
        self.title.become(self._count_title(n))
        self.cur_n, self.cur_median = n, m1

    # ════════════════════════════════════════════════════════════════════════
    # a : single-player plot; normal-width median bar with an upper-right callout
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def show_single(self, run_time=1.5):
        self._prepare()
        self.cur_n = SERIES[0]
        self.cur_median = sd.maxN_median(self.cur_n)
        self.plot = self._build(self.cur_n)
        self.title = self._plain_title("Score Frequencies")
        self.median_label = self._med_label(self.cur_median)
        med_hl, med_riser, med_horiz, med_dot = self.plot.median_group
        rest = VGroup(self.plot.x_axis, self.plot.y_axis, self.plot.y_ticks,
                      self.plot.x_ticks, self.plot.axis_labels)
        callout = VGroup(med_riser, med_horiz, med_dot)
        self._grow_up([*self.plot.bars, med_hl], FadeIn(rest), FadeIn(callout),
                      FadeIn(self.title), FadeIn(self.median_label),
                      run_time=run_time)
        self.wait(0.5)

    # ════════════════════════════════════════════════════════════════════════
    # b–i : best-of-N — morph+pan, median counts up, title N counts on log scale.
    # Later beats (79, 5000, 1M, 8.3B) are the script's population games; the pans
    # get big and the title number climbs on a log scale.
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def best_of_2(self, run_time=3.0):
        self._transition(2, count_title=False, run_time=run_time)   # title crossfade
        self.wait(0.5)

    @subscene
    def best_of_3(self, run_time=3.0):
        self._transition(3, count_title=True, run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_5(self, run_time=3.0):
        self._transition(5, count_title=True, run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_10(self, run_time=3.0):
        self._transition(10, count_title=True, run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_79(self, run_time=3.0):
        self._transition(79, count_title=True, run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_5000(self, run_time=3.0):
        self._transition(5000, count_title=True, run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_1000000(self, run_time=3.0):
        self._transition(1_000_000, count_title=True, run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_8300000000(self, run_time=3.0):
        self._transition(8_300_000_000, count_title=True, run_time=run_time)
        self.wait(0.5)

    @subscene
    def best_of_perfect(self, run_time=4.5, settle=0.35):
        """Finale. ONE play: the number counts continuously up to N* (~5.07e19) over
        the whole ``run_time``, while the title reflows — "Best of" up, number to the
        centre line, "opponents" down (all full-size, moved into the top room) — and
        the plot pans to the perfect-game spike and the median reaches 1575. Those
        MOTIONS use a rate func that finishes by ``settle``*run_time, so they settle
        early while the count keeps going."""
        n = self.n_perfect
        new = self._build(n)
        m1 = sd.maxN_median(n)
        cx = PLOT_C[0]

        # split the current one-line title into movable parts, laid over it so the
        # hand-off is seamless (same words, same size, same spot)
        old = self.title
        oy = old.get_center()[1]
        pre = Text("Best of", font=FONT, font_size=FONT_SIZE_LG, color=BLACK)
        suf = Text("opponents", font=FONT, font_size=FONT_SIZE_LG, color=BLACK)
        num = self._fit_number(self.cur_n)
        pre.move_to([old.get_left()[0] + pre.width / 2, oy, 0])
        suf.move_to([old.get_right()[0] - suf.width / 2, oy, 0])
        num_start = np.array([(pre.get_right()[0] + suf.get_left()[0]) / 2, oy, 0])
        num_end = np.array([cx, STACK_MID, 0])
        num.move_to(num_start)
        self.remove(old)
        self.add(pre, num, suf)

        nt = ValueTracker(np.log(float(self.cur_n)))   # value: counts the whole time
        pt = ValueTracker(0.0)                          # number's move (settles early)
        mt = ValueTracker(self.cur_median)
        num.add_updater(lambda m: m.become(
            self._fit_number(int(round(np.exp(nt.get_value()))))
            .move_to(interpolate(num_start, num_end, pt.get_value()))))
        self.median_label.add_updater(
            lambda mob: mob.become(self._med_label(round(mt.get_value()))))

        # The count, the plot pan and the median all run the FULL run_time (same
        # duration, finishing together — so the number never counts alone). Only
        # the words and the number's slide into place settle early (``settle``).
        ease = squish_rate_func(smooth, 0.0, settle)
        self.play(
            pre.animate(rate_func=ease).move_to([cx, STACK_MID + STACK_GAP, 0]),
            suf.animate(rate_func=ease).move_to([cx, STACK_MID - STACK_GAP, 0]),
            pt.animate(rate_func=ease).set_value(1.0),
            mt.animate.set_value(m1),
            *morph_panning(self.plot, new),
            nt.animate(rate_func=linear).set_value(np.log(float(n))),
            run_time=run_time,
        )
        num.clear_updaters()
        num.become(self._fit_number(n).move_to(num_end))
        self.median_label.clear_updaters()
        self.median_label.become(self._med_label(m1))

        self.title = VGroup(pre, num, suf)
        self.cur_n, self.cur_median, self.plot = n, m1, new
        self.wait(0.5)
