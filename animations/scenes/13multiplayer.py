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
STACK_MID  = 3.2           # finale: y of the number line in the stacked title
STACK_GAP  = 0.30          # finale: edge-to-edge gap from the number to each word
WORD_SHRINK = 0.75         # finale: shrink "Best of"/"opponents" (48pt->36pt) so the
#                            stacked title doesn't crowd the top of the frame

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
        self.means = {}

    def _dist(self, n):
        if n not in self.dists:
            self.dists[n] = sd.maxN_distribution(n)
        return self.dists[n]

    def _center(self, n):
        if n not in self.centers:
            lo, hi = trimmed_range(self._dist(n), MIN_PROB)
            self.centers[n] = (lo + hi) / 2
        return self.centers[n]

    def _mean(self, n):
        """Mean (expected score) of the best-of-n distribution. Unlike the median or
        the trimmed-range centre — both of which JUMP as the tails / CDF-crossing
        shift — the mean is a smooth, continuous function of n. Anchoring the pan's
        window-centre to it makes the slide smooth; the median highlight still snaps
        to its own bar on top of that smooth pan."""
        if n not in self.means:
            d = self._dist(n)
            tot = sum(d.values())
            self.means[n] = (sum(s * p for s, p in d.items()) / tot) if tot else 0.0
        return self.means[n]

    def _wc(self, nb, prev_n, n):
        """Pan window-centre for a checkpoint. Take the MEAN's screen offset from box-
        centre at the beat's START and END (mean − range-centre; a little left, since
        the distribution is right-skewed), move it SMOOTHLY from the start offset to
        the end offset, and place the window so THIS checkpoint's mean lands at the
        interpolated offset. So the mean glides from its start position to its end
        position — and because the mean is smooth in n (the median / range-centre
        JUMP), the slide has no jumps. Endpoints keep the range-centre framing so a
        resting plot stays boxed; the median highlight still snaps to its own bar."""
        lp = np.log(float(prev_n))
        sp = np.log(float(n)) - lp
        fr = (np.log(float(nb)) - lp) / sp if sp else 1.0
        d0 = self._mean(prev_n) - self._center(prev_n)      # mean's screen offset, start
        d1 = self._mean(n) - self._center(n)                # ... and end
        return self._mean(nb) - (d0 + fr * (d1 - d0))       # this mean at the interp offset

    def _build(self, n, wc=None):
        """The bars/axes/ticks ONLY — no median callout (the highlight bar, dashed
        leader, and "Median NNN" label are all scene-owned). ``wc`` overrides the
        window-centre (a beat glides it via _wc, anchored to the smooth mean);
        defaults to the range-centre so a RESTING plot is boxed."""
        return get_panning_histogram(
            self._dist(n), wc if wc is not None else self._center(n),
            self.union[0], self.union[1],
            self.scale_x, center=PLOT_C, width=PLOT_W, height=PLOT_H,
            bar_color=BASE_COLOR, x_tick_step=X_TICK_STEP, y_headroom=Y_HEADROOM,
            y_tick_values=Y_TICKS,
            y_axis_label="Frequency (%)", x_axis_label="Score", title=None,
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
        m = crisp_text(f"Median{chr(0xA0)}{med}", font=FONT, font_size=FONT_SIZE_SM,
                       color=BLACK, weight="BOLD")
        m.move_to([MED_ANCHOR[0] + 0.12, MED_ANCHOR[1], 0], aligned_edge=LEFT)
        return m

    def _grow_up(self, bars, *extra, run_time=1.0):
        for b in bars:
            b.save_state()
            b.stretch(1e-3, dim=1, about_edge=DOWN)
        self.play(*[Restore(b) for b in bars], *extra, run_time=3.0)

    def _med_hl_for(self, score, plot=None):
        """The median highlight: a recoloured COPY of the chart bar at ``score`` in
        ``plot`` (default the live one). As a per-frame updater it IS whichever bar
        matches the counter — it snaps bar-to-bar and rides the pan, instead of
        interpolating between two bars."""
        plot = plot or self.plot
        idx = min(max(int(round(score)) - self.union[0], 0), len(plot.bars) - 1)
        hl = plot.bars[idx].copy().set_fill(MED_COLOR, opacity=1.0).set_stroke(width=0)
        hl.set_z_index(2)
        return hl

    def _med_lead_for(self, score, plot=None):
        """The dashed up-and-over leader (riser + horizontal + dot) from the top of
        the bar at ``score`` to MED_ANCHOR. Shown only at REST — it fades out at the
        start of a beat and back in at the end."""
        plot = plot or self.plot
        idx = min(max(int(round(score)) - self.union[0], 0), len(plot.bars) - 1)
        bar = plot.bars[idx]
        mx, bar_top = bar.get_center()[0], bar.get_top()[1]
        ax, ay = MED_ANCHOR[0], MED_ANCHOR[1]
        riser = DashedVMobject(Line([mx, bar_top, 0], [mx, ay, 0], color=MED_COLOR,
                                    stroke_width=3), num_dashes=5, dashed_ratio=0.55)
        horiz = DashedVMobject(Line([mx, ay, 0], [ax, ay, 0], color=MED_COLOR,
                                    stroke_width=3), num_dashes=12, dashed_ratio=0.55)
        dot = Dot([mx, bar_top, 0], radius=0.05, color=MED_COLOR)
        g = VGroup(riser, horiz, dot)
        g.set_z_index(2)
        return g

    def _beat_seq(self, prev_n, n, m0, m1):
        """N-values + medians to morph through for a beat from ``prev_n`` (median
        ``m0``) to ``n`` (median ``m1``): every checkpoint whose N is strictly inside
        the range. The beat is paced by the opponent count on a LOG scale (see the
        log-weighted sub-morph times), so the median just reaches each checkpoint's
        median as N passes that checkpoint's N. A plateaued median near the top
        (where achievable scores get sparse) is harmless — its sub-morph still has a
        positive log-N width, so no zero-run_time step."""
        inter = [c[0] for c in self.checkpoints if prev_n < c[0] < n]
        seq = [prev_n, *inter, n]
        meds = [m0, *[sd.maxN_median(c) for c in inter], m1]
        return seq, meds

    def _eased_beat(self, seq, run_time):
        """Per-sub-morph (run_time, rate_func) so the opponent count EASES (manim
        ``smooth``) on a LOG scale across the WHOLE beat — the pre-checkpoint feel.
        Each checkpoint sits at its log-N fraction along the smooth curve; a
        sub-morph gets the time between its endpoints' inverse-smooth positions and a
        rate_func that replays just that slice of ``smooth`` — so pan/median/count
        stay in lock-step and the median still reaches each checkpoint as N passes
        it, but the count eases in and out over the beat instead of running at a
        constant log rate."""
        lp = np.log(float(seq[0]))
        span = np.log(float(seq[-1])) - lp

        def sinv(y):                                    # inverse of manim's smooth
            y = min(1.0, max(0.0, y))                    # smooth is a sigmoid
            e = 1.0 / (1.0 + np.exp(5.0))               # sigmoid(-5) (inflection=10)
            p = y * (1.0 - 2.0 * e) + e
            return 0.5 + np.log(p / (1.0 - p)) / 10.0

        fr = [(np.log(float(s)) - lp) / span if span else 0.0 for s in seq]
        tm = [sinv(f) for f in fr]
        out = []
        for i in range(len(seq) - 1):
            ta, dt = tm[i], tm[i + 1] - tm[i]
            fa, df = fr[i], fr[i + 1] - fr[i]
            rate = (lambda s, ta=ta, dt=dt, fa=fa, df=df:
                    (smooth(ta + s * dt) - fa) / df if df else s)
            out.append((run_time * dt, rate))
        return out

    def _morph_chain(self, seq, meds, beat, prev_n, n, mt, nt, run_time,
                     gt=None, extra_first=()):
        """The shared checkpoint-morph loop used by EVERY beat and the finale: each
        sub-morph builds the next mean-anchored plot, morph_panning's it, and advances
        the median tracker ``mt`` and the log-count tracker ``nt`` on that sub-morph's
        eased rate; the dashed leader fades off early in the first step. ``gt`` (if
        given) advances 0..1 in REAL time for the finale's reflow; ``extra_first`` is
        extra anims folded into the first step (e.g. a title crossfade). The caller
        attaches the median_label / med_hl / title / reflow updaters to these trackers
        before calling and tears them down after; ``self.plot`` ends on the last plot."""
        elapsed = 0.0
        for i in range(len(seq) - 1):
            nb, mb = seq[i + 1], meds[i + 1]
            new = self._build(nb, wc=self._wc(nb, prev_n, n))
            rt, rate = beat[i]
            anims = morph_panning(self.plot, new)
            for a in anims:
                a.rate_func = rate                      # slice of smooth (eased over the beat)
            anims.append(mt.animate(rate_func=rate).set_value(mb))
            anims.append(nt.animate(rate_func=rate).set_value(np.log(float(nb))))
            if gt is not None:
                elapsed += rt
                anims.append(gt.animate(rate_func=linear).set_value(min(1.0, elapsed / run_time)))
            if i == 0:                                   # leader off early — no static pause
                anims.append(FadeOut(self.med_lead,
                                     rate_func=squish_rate_func(smooth, 0.0, 0.25)))
                anims += list(extra_first)
            self.play(*anims, run_time=rt)
            self.plot = new

    def _transition(self, n, count_title, run_time=3.0, lead_in=0.5):
        """One ``run_time``-second beat-to-beat animation that morphs THROUGH the
        intermediate checkpoints (real best-of-N distributions whose median crosses
        each multiple of 10). The opponent count N drives it on a LOG scale, EASED
        (manim ``smooth``) over the whole beat, and the median reaches each
        checkpoint's median exactly as N passes that checkpoint's N. The dashed
        median leader fades OUT early in the FIRST step (folded in, so no static
        pause) and draws back IN at the end; the first step crossfades the title."""
        prev_n, m0, m1 = self.cur_n, self.cur_median, sd.maxN_median(n)
        seq, meds = self._beat_seq(prev_n, n, m0, m1)
        beat = self._eased_beat(seq, run_time)
        mt = ValueTracker(m0)
        nt = ValueTracker(np.log(float(prev_n)))
        self.median_label.add_updater(
            lambda mob: mob.become(self._med_label(round(mt.get_value()))))
        self.med_hl.add_updater(                         # snap onto the counter's bar
            lambda h: h.become(self._med_hl_for(round(mt.get_value()))))

        if count_title:                                  # single-line title counts N
            self.title.add_updater(lambda mob: mob.become(
                self._count_title(int(round(np.exp(nt.get_value()))))))
            extra_first = ()
        else:                                            # first count-title beat (1->2):
            new_title = self._count_title(n)             # crossfade plain -> counting title
            extra_first = [FadeOut(self.title), FadeIn(new_title)]

        self._morph_chain(seq, meds, beat, prev_n, n, mt, nt, run_time,
                          extra_first=extra_first)

        self.median_label.clear_updaters()
        self.med_hl.clear_updaters()
        if count_title:
            self.title.clear_updaters()
        else:
            self.title = new_title
        self.median_label.become(self._med_label(m1))
        self.med_hl.become(self._med_hl_for(m1))
        self.title.become(self._count_title(n))
        self.med_lead = self._med_lead_for(m1)          # draw the leader back IN
        self.play(Create(self.med_lead), run_time=lead_in)
        self.cur_n, self.cur_median = n, m1

    # ════════════════════════════════════════════════════════════════════════
    # a : single-player plot; normal-width median bar with an upper-right callout
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def show_single(self):
        self._prepare()
        self.cur_n = SERIES[0]
        self.cur_median = sd.maxN_median(self.cur_n)
        self.plot = self._build(self.cur_n)
        self.title = self._plain_title("Score Frequencies")
        self.median_label = self._med_label(self.cur_median)
        self.med_hl = self._med_hl_for(self.cur_median)
        self.med_lead = self._med_lead_for(self.cur_median)
        rest = VGroup(self.plot.x_axis, self.plot.y_axis, self.plot.y_ticks,
                      self.plot.x_ticks, self.plot.axis_labels)
        self._grow_up([*self.plot.bars, self.med_hl], FadeIn(rest),
                      FadeIn(self.med_lead), FadeIn(self.title),
                      FadeIn(self.median_label), run_time=1.5)

    # ════════════════════════════════════════════════════════════════════════
    # b–i : best-of-N — morph+pan, median counts up, title N counts on log scale.
    # Later beats (79, 5000, 1M, 8.3B) are the script's population games; the pans
    # get big and the title number climbs on a log scale.
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def best_of_2(self):
        self._transition(2, count_title=False, run_time=3.0)   # title crossfade

    @subscene
    def best_of_3(self):
        self._transition(3, count_title=True, run_time=3.0)

    @subscene
    def best_of_5(self):
        self._transition(5, count_title=True, run_time=3.0)

    @subscene
    def best_of_10(self):
        self._transition(10, count_title=True, run_time=3.0)

    @subscene
    def best_of_79(self):
        self._transition(79, count_title=True, run_time=3.0)

    @subscene
    def best_of_5000(self):
        self._transition(5000, count_title=True, run_time=3.0)

    @subscene
    def best_of_1000000(self):
        self._transition(1_000_000, count_title=True, run_time=3.0)

    @subscene
    def best_of_8300000000(self):
        self._transition(8_300_000_000, count_title=True, run_time=3.0)

    def _setup_perfect(self, run_time, settle):
        """Build the finale's split title over the current one-line title — "Best of"
        (up-then-over, shrinking), the number (to the centre line, counting) and
        "opponents" (down-then-over) — and attach its reflow updaters plus the
        median / log-count / beat-time trackers. Owns self.pre / self.num / self.suf.
        The reflow rides a beat-TIME ease that settles by ``settle`` (kept separate
        from the already-eased count so it doesn't double-ease into a wobble). Returns
        (seq, meds, beat, mt, nt, gt) for _morph_chain to run and advance."""
        n, prev_n, m0 = self.n_perfect, self.cur_n, self.cur_median
        seq, meds = self._beat_seq(prev_n, n, m0, sd.maxN_median(n))
        beat = self._eased_beat(seq, run_time)
        cx = PLOT_C[0]

        # split the one-line title into movable parts laid over it (seamless hand-off)
        old = self.title
        oy = old.get_center()[1]
        pre = Text("Best of", font=FONT, font_size=FONT_SIZE_LG, color=BLACK)
        suf = Text("opponents", font=FONT, font_size=FONT_SIZE_LG, color=BLACK)
        pre.move_to([old.get_left()[0] + pre.width / 2, oy, 0])
        suf.move_to([old.get_right()[0] - suf.width / 2, oy, 0])
        pre_start, suf_start = pre.get_center().copy(), suf.get_center().copy()
        pre_base, suf_base = pre.copy(), suf.copy()      # full-size at the split; shrink en route
        # number centred at STACK_MID, the SHRUNK words an equal STACK_GAP above/below
        num_h = self._fit_number(prev_n).height
        pre_end = np.array([cx, STACK_MID + num_h / 2 + STACK_GAP + pre.height * WORD_SHRINK / 2, 0])
        suf_end = np.array([cx, STACK_MID - num_h / 2 - STACK_GAP - suf.height * WORD_SHRINK / 2, 0])
        num_start = np.array([(pre.get_right()[0] + suf.get_left()[0]) / 2, oy, 0])
        num_end = np.array([cx, STACK_MID, 0])
        num = self._fit_number(prev_n).move_to(num_start)
        self.remove(old)
        self.add(pre, num, suf)
        self.pre, self.suf, self.num = pre, suf, num
        self._pre_end, self._suf_end, self._num_end = pre_end, suf_end, num_end
        self._pre_base, self._suf_base = pre_base, suf_base

        mt = ValueTracker(m0)
        nt = ValueTracker(np.log(float(prev_n)))
        gt = ValueTracker(0.0)                          # beat time fraction (0..1)
        reflow = lambda: smooth(min(1.0, gt.get_value() / settle)) if settle else 1.0

        def elbow(start, end, p):
            corner = np.array([start[0], end[1], 0.0])   # L-path: vertical, then over
            v, h = abs(corner[1] - start[1]), abs(end[0] - corner[0])
            f = v / (v + h) if (v + h) else 0.0
            if p <= f:
                return interpolate(start, corner, p / f) if f else corner
            return interpolate(corner, end, (p - f) / (1 - f)) if f < 1 else corner

        self.median_label.add_updater(
            lambda mob: mob.become(self._med_label(round(mt.get_value()))))
        self.med_hl.add_updater(
            lambda h: h.become(self._med_hl_for(round(mt.get_value()))))
        pre.add_updater(lambda m: m.become(pre_base.copy()
            .scale(interpolate(1.0, WORD_SHRINK, reflow()))
            .move_to(elbow(pre_start, pre_end, reflow()))))
        suf.add_updater(lambda m: m.become(suf_base.copy()
            .scale(interpolate(1.0, WORD_SHRINK, reflow()))
            .move_to(elbow(suf_start, suf_end, reflow()))))
        num.add_updater(lambda m: m.become(
            self._fit_number(int(round(np.exp(nt.get_value()))))
            .move_to(interpolate(num_start, num_end, reflow()))))
        return seq, meds, beat, mt, nt, gt

    def _finish_perfect(self):
        """Clear the finale updaters and settle every piece on its final value — the
        median at N*'s value, the words shrunk at their stacked ends, the number at
        N* — then re-build the median leader for the closing draw-in and record the
        end state (cur_n / cur_median / title)."""
        n = self.n_perfect
        m1 = sd.maxN_median(n)
        for mob in (self.median_label, self.med_hl, self.pre, self.suf, self.num):
            mob.clear_updaters()
        self.median_label.become(self._med_label(m1))
        self.med_hl.become(self._med_hl_for(m1))
        self.pre.become(self._pre_base.copy().scale(WORD_SHRINK).move_to(self._pre_end))
        self.suf.become(self._suf_base.copy().scale(WORD_SHRINK).move_to(self._suf_end))
        self.num.become(self._fit_number(n).move_to(self._num_end))
        self.med_lead = self._med_lead_for(m1)          # ready for the closing Create
        self.title = VGroup(self.pre, self.num, self.suf)
        self.cur_n, self.cur_median = n, m1              # self.plot set by _morph_chain

    @subscene
    def best_of_perfect(self):
        """Finale — the shared morph chain (pan / eased log-N count / median snap) PLUS
        a one-off title reflow, both built in _setup_perfect. Only the animation and
        its timings live here, so it's easy to tune: the morph runs over ``run_time``
        (the reflow settling by ``settle``), then the median leader draws back in over
        ``lead_in``."""
        run_time, settle, lead_in = 5.0, 0.35, 0.5       # finale timings (tweak here)
        seq, meds, beat, mt, nt, gt = self._setup_perfect(run_time, settle)
        self._morph_chain(seq, meds, beat, self.cur_n, self.n_perfect, mt, nt, run_time, gt=gt)
        self._finish_perfect()
        self.play(Create(self.med_lead), run_time=lead_in)
