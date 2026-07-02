from pathlib import Path
import sys

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from bpkfigures.style import (FONT_SIZE_SM, ACCENT_GOLD, ACCENT_ORANGE, ACCENT_RED,
                              ACCENT_GREEN, ACCENT_PURPLE, ACCENT_PINK)
from bpkfigures.card import get_card
from bpkfigures.line_graph import get_line_graph, line_point
from assets import line_data as ld

# ── plot geometry / look (knobs for the user) ─────────────────────────────────
# The plot sits a touch high inside the card so the "Turn" x-axis label clears the
# rounded bottom edge; the title clears the top.
CARD_C = [0, 0, 0]
CARD_W = 13.4
CARD_H = 7.4
PLOT_C = [-1.15, -0.05, 0]
PLOT_W = 8.0
PLOT_H = 4.35
Y_MAX  = 35            # headroom above the tallest line (Large Straight ≈ 32.7)

# One colour per line (drawn / listed in the assets/line_data.LINES order:
# Small Straight, Large Straight, Yahtzee, 3 of a Kind, 4 of a Kind, Full House).
# Assigned so that no two lines that finish close together share a similar hue —
# in particular the near-identical gold/orange are kept well apart (Small Straight
# vs Full House, not the two straights).
LINE_COLORS = [ACCENT_GOLD, ACCENT_GREEN, ACCENT_RED,
               ACCENT_PINK, ACCENT_PURPLE, ACCENT_ORANGE]

# line indices (match LINES order) so the highlight beats read clearly
SM_STRAIGHT, LG_STRAIGHT, YAHTZEE, THREE_KIND, FOUR_KIND, FULL_HOUSE = range(6)

BASE_SW  = 4.0         # normal line stroke
FOCUS_SW = 7.0         # highlighted line stroke
DIM_OP   = 0.16        # opacity of de-emphasised lines/labels

# small manual y-nudges (screen units) to unstack end labels whose lines finish
# close together at round 13 (Large Straight ≈ 10.4 vs Full House ≈ 9.2)
LABEL_NUDGE = {LG_STRAIGHT: 0.12, FULL_HOUSE: -0.12}


class LineGraph(YahtzeeScene):
    def setup_scene(self):
        pass

    # ── shared builders ──────────────────────────────────────────────────────
    def _setup_plot(self):
        """The card + full 6-line plot (lines built but NOT yet shown) + a colour
        end-label per line. Built once; beats reveal the pieces over time."""
        data = ld.scene08_lines()
        self.rounds = data["rounds"]
        self.line_info = data["lines"]                 # [{key,label,values}]

        series = [{"label": ln["label"], "values": ln["values"],
                   "color": LINE_COLORS[i]}
                  for i, ln in enumerate(self.line_info)]
        self.plot = get_line_graph(
            series, self.rounds, center=PLOT_C, width=PLOT_W, height=PLOT_H,
            y_min=0.0, y_max=Y_MAX, x_tick_step=1,
            title="Average Points if Unfilled",
            x_axis_label="Turn", y_axis_label="Avg Points",
            line_stroke=BASE_SW, show_dots=False,
        )

        # the static "frame" = everything except the data lines
        self.frame = VGroup(*[m for m in (
            self.plot.x_axis, self.plot.y_axis, self.plot.x_ticks,
            self.plot.y_ticks, self.plot.x_axis_label_text,
            self.plot.y_axis_label_text, self.plot.title_text) if m is not None])

        # colour end-labels, parked just right of each line's round-13 endpoint
        self.end_labels = VGroup()
        for i, ln in enumerate(self.line_info):
            end = line_point(self.plot.plot_geom, self.rounds[-1], ln["values"][-1])
            lab = crisp_text(ln["label"], font=FONT, font_size=FONT_SIZE_SM * 0.8,
                             color=LINE_COLORS[i])
            lab.next_to(end, RIGHT, buff=0.15)
            lab.shift(UP * LABEL_NUDGE.get(i, 0.0))
            self.end_labels.add(lab)

    def _setup_keep_drop(self):
        """A tall double-arrow at the far right with 'try to keep' at the top and
        'fine to drop' at the bottom — high on the chart = worth keeping, low =
        safe to zero out."""
        top = PLOT_C[1] + PLOT_H / 2
        bot = PLOT_C[1] - PLOT_H / 2
        x = 5.6
        self.kd_arrow = DoubleArrow([x, bot + 0.15, 0], [x, top - 0.15, 0],
                                    color=BLACK, buff=0, stroke_width=4,
                                    tip_length=0.22)
        keep = crisp_text("try to keep", font=FONT, font_size=FONT_SIZE_SM * 0.8,
                          color=BLACK)
        drop = crisp_text("fine to drop", font=FONT, font_size=FONT_SIZE_SM * 0.8,
                          color=BLACK)
        keep.next_to(self.kd_arrow, UP, buff=0.12)
        drop.next_to(self.kd_arrow, DOWN, buff=0.12)
        self.kd_labels = VGroup(keep, drop)

    def _focus(self, idxs, run_time):
        """Emphasise the lines (and their end-labels) whose indices are in ``idxs``
        by thickening them and dimming the rest. ``idxs=None`` (or all) restores
        every line to normal. Reconfigures from whatever the current state is."""
        focus = set(range(len(self.line_info))) if idxs is None else set(idxs)
        anims = []
        for i, line in enumerate(self.plot.lines):
            on = i in focus
            anims.append(line.animate.set_stroke(
                width=FOCUS_SW if on else BASE_SW, opacity=1.0 if on else DIM_OP))
            anims.append(self.end_labels[i].animate.set_opacity(
                1.0 if on else DIM_OP))
        self.play(*anims, run_time=run_time)

    # ════════════════════════════════════════════════════════════════════════
    # a : axes + title + keep/drop scale, no data yet
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def axes_in(self):
        run_time = 1.2
        self._setup_plot()
        self._setup_keep_drop()
        self.card = get_card(CARD_W, CARD_H, center=CARD_C)
        self.card.set_z_index(-1)
        self.play(FadeIn(self.card), run_time=run_time * 0.6)
        self.play(FadeIn(self.frame),
                  GrowFromCenter(self.kd_arrow), FadeIn(self.kd_labels),
                  run_time=run_time)

    # ════════════════════════════════════════════════════════════════════════
    # b : the small-straight line (the worked example)
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def small_straight(self):
        run_time = 2.0
        self.play(Create(self.plot.lines[SM_STRAIGHT]),
                  FadeIn(self.end_labels[SM_STRAIGHT]), run_time=run_time)

    # ════════════════════════════════════════════════════════════════════════
    # c : fill in the rest of the lines
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def fill_rest(self):
        run_time = 2.5
        rest = [i for i in range(len(self.line_info)) if i != SM_STRAIGHT]
        self.play(
            *[Create(self.plot.lines[i]) for i in rest],
            *[FadeIn(self.end_labels[i]) for i in rest],
            run_time=run_time, lag_ratio=0.08,
        )

    # ════════════════════════════════════════════════════════════════════════
    # d : lowest line = safest to zero — 4-of-a-kind, then yahtzee
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def highlight_low(self):
        run_time = 0.8
        hold = 1.5
        self._focus([FOUR_KIND], run_time)
        self.wait(hold)
        self._focus([YAHTZEE], run_time)
        self.wait(hold)
        self._focus(None, run_time)

    # ════════════════════════════════════════════════════════════════════════
    # e : top of the chart — large straight (starts top), small straight (ends top)
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def highlight_top(self):
        run_time = 0.8
        hold = 1.5
        self._focus([LG_STRAIGHT], run_time)
        self.wait(hold)
        self._focus([SM_STRAIGHT], run_time)
        self.wait(hold)
        self._focus(None, run_time)

    # ════════════════════════════════════════════════════════════════════════
    # f : takeaways — safe to drop (4-kind + yahtzee), then keep (sm str, 3-kind,
    #     lg str)
    # ════════════════════════════════════════════════════════════════════════
    @subscene
    def takeaways(self):
        run_time = 0.9
        hold = 2.0
        self._focus([FOUR_KIND, YAHTZEE], run_time)
        self.wait(hold)
        self._focus([SM_STRAIGHT, THREE_KIND, LG_STRAIGHT], run_time)
        self.wait(hold)
