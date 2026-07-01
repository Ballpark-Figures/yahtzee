from pathlib import Path
import sys

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import get_die, morph_dice
from assets import dp_data as dp


# ── the last-turn example card: every box filled EXCEPT Large Straight ─────────
# scorecard box order: 0-5 Ones..Sixes, 6=3Kind, 7=4Kind, 8=FullHouse,
# 9=SmStraight, 10=LgStraight, 11=Yahtzee, 12=Chance, 13=Yahtzee bonus.
FILL = {0: 3, 1: 6, 2: 9, 3: 12, 4: 15, 5: 18,   # top = 63 → bonus earned
        6: 22, 7: 0, 8: 25, 9: 30, 11: 50, 12: 17}   # (10 = Lg Straight stays open)

GRAY = "#9A9483"          # gray placeholder "0" in an empty candidate box


class DynamicProgramming(YahtzeeScene):
    """Scene 04 — dynamic programming: work backward from the end of the game.

    Running example = the LAST turn with only one box open, so every EV/prob is
    an exact single-box expectation (all numbers from assets/dp_data.py).

      intro_card        — empty card fills to "all but Lg Straight"; a 12345 final
                          roll scores the last box.
      second_reroll     — 12346, keep 1234 with ONE reroll left: 40 pts / 0 pts /
                          Avg pts counters on the right.
      reroll_cycle      — cycle the kept set (34 / 234 / 246) → back to 1234 (best).
      other_rolls       — a couple more rolls with their best keep + numbers.
      first_reroll      — step back to the FIRST reroll (12446, TWO left): Avg pts
                          only, settle on keeping 24.
      turn_ev           — morph a few first rolls with per-roll EVs → one turn EV.
      box_choice        — 11134 with 3Kind and 4Kind both open: compare "avg points
                          after" and fill the better box.
      backward_sweep    — (rough) empty the card box by box while an "avg points
                          remaining" counter climbs toward the full-game ~255.
    """

    # ── layout knobs ──────────────────────────────────────────────────────────
    DIE   = 0.72
    DBUFF = 0.16
    DCX   = 1.35           # centre-x of the analysed dice row
    TOP_Y = 2.7            # "top position" row (final roll / box-choice roll)
    ROW_Y = 1.15          # the row where reroll decisions are analysed

    PANEL_LX = 4.05        # left edge of the stat labels
    PANEL_NX = 6.35        # left edge of the stat numbers (grow rightward)
    STAT_FS  = 34
    LBL_FS   = 30

    # ── small helpers ─────────────────────────────────────────────────────────
    def _dice_row(self, values, cy, *, cx=None, size=None):
        cx = self.DCX if cx is None else cx
        size = self.DIE if size is None else size
        dice = [get_die(v, size=size) for v in values]
        VGroup(*dice).arrange(RIGHT, buff=self.DBUFF).move_to([cx, cy, 0])
        return dice

    def _set_keep(self, dice, keep_idxs, *, run_time, dim=0.25):
        """Fade non-kept dice down to `dim` and kept dice back to full."""
        keep_idxs = set(keep_idxs)
        self.play(*[d.animate.set_opacity(1.0 if i in keep_idxs else dim)
                    for i, d in enumerate(dice)], run_time=run_time)

    def _label(self, text, x, y, *, fs=None, color=BLACK, anchor=LEFT):
        fs = self.STAT_FS if fs is None else fs
        m = crisp_text(text, font_size=fs, color=color, font=FONT, weight="BOLD")
        m.move_to([x, y, 0], aligned_edge=anchor)
        return m

    def _num(self, value, fmt, x, y, *, color=BLACK, anchor=LEFT):
        return self._label(fmt(value), x, y, color=color, anchor=anchor)

    def _count(self, specs, run_time):
        """Animate a set of crisp_text numbers by rebuilding them each frame from a
        ValueTracker (the project's LaTeX-free counter pattern, see scene 13).
        Each spec: dict(mob, fmt, x, y, start, target, color?, anchor?). Updaters
        are cleared at the end so nothing unpicklable rides into the snapshot."""
        live = []
        anims = []
        for s in specs:
            t = ValueTracker(s["start"])
            fmt, x, y = s["fmt"], s["x"], s["y"]
            color = s.get("color", BLACK)
            anchor = s.get("anchor", LEFT)

            def upd(mob, t=t, fmt=fmt, x=x, y=y, color=color, anchor=anchor):
                new = crisp_text(fmt(t.get_value()), font_size=self.STAT_FS,
                                 color=color, font=FONT, weight="BOLD")
                new.move_to([x, y, 0], aligned_edge=anchor)
                mob.become(new)

            s["mob"].add_updater(upd)
            live.append((s, t))
            anims.append(t.animate.set_value(s["target"]))
        self.play(*anims, run_time=run_time)
        for s, t in live:
            s["mob"].clear_updaters()
            final = crisp_text(s["fmt"](s["target"]), font_size=self.STAT_FS,
                               color=s.get("color", BLACK), font=FONT, weight="BOLD")
            final.move_to([s["x"], s["y"], 0], aligned_edge=s.get("anchor", LEFT))
            s["mob"].become(final)

    @staticmethod
    def _pct(v):
        return f"{v:.1f}%"

    @staticmethod
    def _ev(v):
        return f"{v:.2f}"

    # ══════════════════════════════════════════════════════════════════════════
    # a : empty card → fill all but Lg Straight → a 12345 final roll scores it
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def intro_card(self, run_time=1.0):
        self.card = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        self.play(FadeIn(self.card, shift=RIGHT * 1.5), run_time=run_time)
        self.wait(0.2)
        # "fill in everything but large straight"
        self.card.transition(self, dict(FILL), run_time=1.4)
        self.wait(0.3)
        # "bring in dice to top position" — a 12345 last roll (a large straight)
        dice = self._dice_row([1, 2, 3, 4, 5], self.TOP_Y)
        self.play(*[FadeIn(d, shift=UP * 0.6) for d in dice], run_time=0.8)
        self.wait(0.4)
        # "score the final dice" into the one open box (the dice return to the row
        # afterwards — large_straight keeps them — so clear them before the reroll
        # analysis builds a fresh row below).
        self.card.large_straight(self, dice, y=self.TOP_Y)
        self.wait(0.4)
        self.play(FadeOut(VGroup(*dice)), run_time=0.4)
        self.wait(0.2)

    # ══════════════════════════════════════════════════════════════════════════
    # b : second (last) reroll — 12346, keep 1234, show 40/0/avg counters
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def second_reroll(self, run_time=0.8):
        self.nums = dp.scene04_numbers()
        # re-open Large Straight so the same box is the target we reroll for
        self.card.transition(self, {10: None}, run_time=0.6)

        self.dice = self._dice_row([1, 2, 3, 4, 6], self.ROW_Y)
        self.play(*[FadeIn(d, shift=UP * 0.5) for d in self.dice], run_time=run_time)
        self.wait(0.2)

        # right-hand stat panel (labels static, numbers count)
        ys = [self.ROW_Y + 0.75, self.ROW_Y, self.ROW_Y - 0.75]
        self.lbl_p40 = self._label("40 pts:", self.PANEL_LX, ys[0])
        self.lbl_p0  = self._label("0 pts:",  self.PANEL_LX, ys[1])
        self.lbl_ev  = self._label("Avg pts:", self.PANEL_LX, ys[2])
        self.n_p40 = self._num(0, self._pct, self.PANEL_NX, ys[0])
        self.n_p0  = self._num(0, self._pct, self.PANEL_NX, ys[1])
        self.n_ev  = self._num(0, self._ev,  self.PANEL_NX, ys[2])
        self.panel_ys = ys
        panel = VGroup(self.lbl_p40, self.lbl_p0, self.lbl_ev,
                       self.n_p40, self.n_p0, self.n_ev)
        self.play(FadeIn(panel), run_time=0.5)

        # keep 1234 (dice[4] is the 6) and count the numbers up from 0
        self._set_keep(self.dice, [0, 1, 2, 3], run_time=0.5)
        self._retarget("1234", run_time=0.9, start=0.0)
        self.wait(0.5)

    # keep-name → the physical dice indices kept (dice are 1,2,3,4,6 left→right)
    _KEEP_IDX = {"1234": [0, 1, 2, 3], "34": [2, 3], "234": [1, 2, 3], "246": [1, 3, 4]}

    def _retarget(self, name, *, run_time, start=None):
        """Point the 40/0/avg counters at the values for keep `name`."""
        d = self.nums["second_reroll"][name]
        ys = self.panel_ys
        cur = None if start is None else start
        self._count([
            {"mob": self.n_p40, "fmt": self._pct, "x": self.PANEL_NX, "y": ys[0],
             "start": (self.n_p40_val if cur is None else cur), "target": d["p40"] * 100},
            {"mob": self.n_p0,  "fmt": self._pct, "x": self.PANEL_NX, "y": ys[1],
             "start": (self.n_p0_val if cur is None else cur), "target": d["p0"] * 100},
            {"mob": self.n_ev,  "fmt": self._ev,  "x": self.PANEL_NX, "y": ys[2],
             "start": (self.n_ev_val if cur is None else cur), "target": d["ev"]},
        ], run_time)
        self.n_p40_val, self.n_p0_val, self.n_ev_val = d["p40"] * 100, d["p0"] * 100, d["ev"]

    # ══════════════════════════════════════════════════════════════════════════
    # c : cycle the kept set, counters move, return to 1234 (best → green)
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def reroll_cycle(self, run_time=0.6):
        for name in ["34", "234", "246"]:
            self._set_keep(self.dice, self._KEEP_IDX[name], run_time=run_time)
            self._retarget(name, run_time=0.8)
            self.wait(0.35)
        # back to the best keep, then flag it (EV turns green)
        self._set_keep(self.dice, self._KEEP_IDX["1234"], run_time=run_time)
        self._retarget("1234", run_time=0.8)
        self.play(self.n_ev.animate.set_color(SCORE_GREEN),
                  self.lbl_ev.animate.set_color(SCORE_GREEN), run_time=0.5)
        self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # d : a couple more rolls with their best keep + numbers already in place
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def other_rolls(self, run_time=0.6):
        # reset the EV colour back to black for the fresh examples
        self.play(self.n_ev.animate.set_color(BLACK),
                  self.lbl_ev.animate.set_color(BLACK), run_time=0.3)
        for values in ([2, 3, 4, 5, 6], [1, 2, 3, 5, 5]):
            morph_dice(self, self.dice, values, run_time=0.5)
            for d in self.dice:
                d.set_opacity(1.0)
            keep_vec, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 1)
            keep_idxs = self._keep_indices(values, keep_vec)
            self._set_keep(self.dice, keep_idxs, run_time=run_time)
            dist = dp.score_dist_keep(None, keep_vec, dp.LARGE_STRAIGHT)
            self._count([
                {"mob": self.n_p40, "fmt": self._pct, "x": self.PANEL_NX,
                 "y": self.panel_ys[0], "start": self.n_p40_val, "target": dist.get(40, 0.0) * 100},
                {"mob": self.n_p0,  "fmt": self._pct, "x": self.PANEL_NX,
                 "y": self.panel_ys[1], "start": self.n_p0_val, "target": dist.get(0, 0.0) * 100},
                {"mob": self.n_ev,  "fmt": self._ev,  "x": self.PANEL_NX,
                 "y": self.panel_ys[2], "start": self.n_ev_val, "target": ev},
            ], run_time=0.8)
            self.n_p40_val = dist.get(40, 0.0) * 100
            self.n_p0_val = dist.get(0, 0.0) * 100
            self.n_ev_val = ev
            self.wait(0.5)

    @staticmethod
    def _keep_indices(values, keep_vec):
        """Which physical dice (by left→right position in `values`) make up the
        keep count-vector `keep_vec`."""
        need = list(keep_vec)
        idxs = []
        for i, v in enumerate(values):
            if need[v - 1] > 0:
                idxs.append(i)
                need[v - 1] -= 1
        return idxs

    # ══════════════════════════════════════════════════════════════════════════
    # e : step back to the FIRST reroll — 12446, avg pts only, settle on 24
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def first_reroll(self, run_time=0.6):
        # "only show avg points, and not probs of 40 and 0" — drop the two prob rows
        self.play(FadeOut(VGroup(self.lbl_p40, self.lbl_p0, self.n_p40, self.n_p0)),
                  run_time=0.4)
        morph_dice(self, self.dice, [1, 2, 4, 4, 6], run_time=0.5)
        for d in self.dice:
            d.set_opacity(1.0)
        self.wait(0.2)

        keep_idx = {"124": [0, 1, 2], "24": [1, 2], "246": [1, 2, 4]}
        for name in ["124", "24", "246"]:
            self._set_keep(self.dice, keep_idx[name], run_time=run_time)
            ev = self.nums["first_reroll"][name]["ev"]
            self._count([{"mob": self.n_ev, "fmt": self._ev, "x": self.PANEL_NX,
                          "y": self.panel_ys[2], "start": self.n_ev_val, "target": ev}], 0.8)
            self.n_ev_val = ev
            self.wait(0.35)
        # best = keep 24
        self._set_keep(self.dice, keep_idx["24"], run_time=run_time)
        ev = self.nums["first_reroll"]["24"]["ev"]
        self._count([{"mob": self.n_ev, "fmt": self._ev, "x": self.PANEL_NX,
                      "y": self.panel_ys[2], "start": self.n_ev_val, "target": ev}], 0.6)
        self.n_ev_val = ev
        self.play(self.n_ev.animate.set_color(SCORE_GREEN),
                  self.lbl_ev.animate.set_color(SCORE_GREEN), run_time=0.5)
        self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # f : morph a few first rolls (EV above each), then collapse to a turn EV
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def turn_ev(self, run_time=0.6):
        self.play(FadeOut(VGroup(self.lbl_ev, self.n_ev)), run_time=0.3)
        self.n_ev = self.lbl_ev = None

        above = self._label("Avg pts: 0.00", self.DCX, self.ROW_Y + 1.1, anchor=ORIGIN)
        self.play(FadeIn(above), run_time=0.3)
        prev = 0.0
        for values in ([1, 2, 4, 4, 6], [2, 3, 4, 5, 6], [1, 1, 3, 4, 5]):
            morph_dice(self, self.dice, values, run_time=0.5)
            for d in self.dice:
                d.set_opacity(1.0)
            _, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 2)
            self._count([{"mob": above, "fmt": lambda v: f"Avg pts: {v:.2f}",
                          "x": self.DCX, "y": self.ROW_Y + 1.1, "start": prev,
                          "target": ev, "anchor": ORIGIN}], 0.7)
            prev = ev
            self.wait(0.4)

        # collapse to the whole-turn EV (all-out for Large Straight)
        turn = self.nums["turn_values"]["large_straight"]
        self.play(FadeOut(VGroup(*self.dice)), FadeOut(above), run_time=0.5)
        self.dice = None
        lbl = self._label("Avg pts this turn:", self.DCX - 0.4, self.ROW_Y, anchor=ORIGIN)
        num = self._label("0.00", self.DCX + 2.6, self.ROW_Y, color=SCORE_GREEN, anchor=ORIGIN)
        self.play(FadeIn(lbl), FadeIn(num), run_time=0.4)
        self._count([{"mob": num, "fmt": self._ev, "x": self.DCX + 2.6, "y": self.ROW_Y,
                      "start": 0.0, "target": turn, "color": SCORE_GREEN, "anchor": ORIGIN}], 0.9)
        self.turn_lbl, self.turn_num = lbl, num
        self.wait(0.6)

    # ══════════════════════════════════════════════════════════════════════════
    # g : box choice — 11134 with 3Kind & 4Kind open; compare "avg points after"
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def box_choice(self, run_time=0.6):
        self.play(FadeOut(VGroup(self.turn_lbl, self.turn_num)), run_time=0.3)
        self.turn_lbl = self.turn_num = None
        # open up 3Kind and 4Kind (Lg Straight stays scored from the running example)
        self.card.transition(self, {6: None, 7: None}, run_time=0.6)
        self.wait(0.2)

        dice = self._dice_row([1, 1, 1, 3, 4], self.TOP_Y)
        self.play(*[FadeIn(d, shift=UP * 0.5) for d in dice], run_time=0.6)
        self.wait(0.2)

        # gray placeholder 0's in the two candidate boxes + lines from the dice
        c3 = self.card.value_cells[6].get_center()
        c4 = self.card.value_cells[7].get_center()
        z3 = self._label("0", c3[0], c3[1], fs=self.STAT_FS, color=GRAY, anchor=ORIGIN)
        z4 = self._label("0", c4[0], c4[1], fs=self.STAT_FS, color=GRAY, anchor=ORIGIN)
        dice_anchor = VGroup(*dice).get_bottom()
        ln3 = Line(self.card.value_cells[6].get_right(), dice_anchor,
                   stroke_color=GRAY, stroke_width=2.0)
        ln4 = Line(self.card.value_cells[7].get_right(), dice_anchor,
                   stroke_color=GRAY, stroke_width=2.0)
        self.play(FadeIn(z3), FadeIn(z4), Create(ln3), Create(ln4), run_time=0.6)

        box = self.nums["box_choice"]
        ev3 = box["fill_3kind"]["total"]   # score 3Kind now (10) + keep 4Kind open
        ev4 = box["fill_4kind"]["total"]   # zero 4Kind now (0) + keep 3Kind open
        lab3 = self._label(f"Avg after: {ev3:.1f}", -1.4, c3[1], fs=self.LBL_FS, anchor=LEFT)
        lab4 = self._label(f"Avg after: {ev4:.1f}", -1.4, c4[1], fs=self.LBL_FS, anchor=LEFT)
        self.play(FadeIn(lab3), FadeIn(lab4), run_time=0.5)
        self.wait(0.6)

        # NOTE (flag to user): the computed winner here is 3-of-a-Kind (fill the 10),
        # NOT the 4-of-a-Kind the script GUESSED ("presumably the 4kind"). Going with
        # the real number; highlight whichever box wins.
        fill_3k = ev3 >= ev4
        self.play(FadeOut(VGroup(ln3, ln4, z3, z4, lab3, lab4)), run_time=0.4)
        if fill_3k:
            self.card.three_of_a_kind(self, dice)          # 11134 → 10 in 3-of-a-Kind
        else:
            self.card.four_of_a_kind(self, dice)
        self.wait(0.4)
        # the dice return to the row after scoring — clear them before the sweep
        self.play(FadeOut(VGroup(*dice)), run_time=0.4)
        self.wait(0.4)

    # ══════════════════════════════════════════════════════════════════════════
    # h : (ROUGH) empty the card box-by-box while "avg points remaining" climbs
    #     toward the full-game value (~255). Intermediate values are illustrative
    #     placeholders — flagged for the user (need whole-game solver EVs).
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def backward_sweep(self, run_time=0.8):
        lbl = self._label("Avg points remaining:", 1.6, self.TOP_Y, anchor=ORIGIN)
        num = self._label("0", 4.4, self.TOP_Y, color=SCORE_GREEN, anchor=ORIGIN)
        self.play(FadeIn(lbl), FadeIn(num), run_time=0.4)

        # placeholder ladder of "remaining EV" as boxes empty (rough; ends ~255)
        steps = [(12, 40), (9, 95), (8, 140), (5, 180), (2, 215), (0, 255)]
        prev = 0.0
        for box, remaining in steps:
            self.card.transition(self, {box: None}, run_time=0.5)
            self._count([{"mob": num, "fmt": lambda v: f"{v:.0f}", "x": 4.4,
                          "y": self.TOP_Y, "start": prev, "target": remaining,
                          "color": SCORE_GREEN, "anchor": ORIGIN}], 0.5)
            prev = remaining
            self.wait(0.25)
        self.wait(0.8)
