from pathlib import Path
import sys

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice, BAND_YS, slot_x
from assets import dp_data as dp


# ── the last-turn example card: every box filled EXCEPT Large Straight ─────────
# scorecard box order: 0-5 Ones..Sixes, 6=3Kind, 7=4Kind, 8=FullHouse,
# 9=SmStraight, 10=LgStraight, 11=Yahtzee, 12=Chance, 13=Yahtzee bonus.
FILL = {0: 3, 1: 6, 2: 9, 3: 12, 4: 15, 5: 18,   # top = 63 → bonus earned
        6: 22, 7: 0, 8: 25, 9: 30, 11: 50, 12: 17}   # (10 = Lg Straight stays open)

GRAY = "#9A9483"          # gray placeholder "0" in an empty candidate box


class DynamicProgramming(YahtzeeScene):
    """Scene 04 — dynamic programming: work backward from the end of the game.

    The dice live in the standard 4-band playfield (the 3 guide lines + BAND_YS,
    like 02rules / 99test). Beat a rolls a real turn UP the rows into a large
    straight; the backward walk then steps the dice DOWN one row per stage —

        band 3 (top)  = final roll  (just fill the open box)
        band 2        = 2nd (last) reroll decision
        band 1        = 1st reroll decision
        band 0        = start of the turn (whole-turn EV)

    — with each stage's odds shown in the row just above the dice. Every EV/prob
    is an exact single-box expectation from assets/dp_data.py.

      intro_card     — card fills to "all but Lg Straight"; a real turn rolls up
                       the rows to 12345 and scores it.
      second_reroll  — dice drop to band 2 → 12346; keep 1234 (1 reroll left):
                       40 pts / 0 pts / Avg pts counters in the row above.
      reroll_cycle   — cycle the kept set (34 / 234 / 246) → back to 1234 (best).
      other_rolls    — a couple more rolls with their best keep + numbers.
      first_reroll   — dice drop to band 1 → 12446 (2 rerolls left): Avg pts only,
                       settle on keeping 24.
      turn_ev        — a few first rolls (EVs above) → dice to band 0, one turn EV.
      box_choice     — 11134 back at the top with 3Kind & 4Kind open: compare
                       "avg points after" via lines to the two boxes.
      backward_sweep — (rough) empty the card box by box while an "avg points
                       remaining" counter climbs toward the full-game ~255.
    """

    # ── stat-panel layout (the odds sit in the row ABOVE the dice) ────────────
    PL, PLN = -0.3, 1.7        # "40 pts:" / "0 pts:" labels + their numbers
    PR, PRN = 3.6, 5.7         # "Avg pts:" label + its number
    PANEL_FS = 32

    # ── small helpers ─────────────────────────────────────────────────────────
    def _shift_band(self, dice, band, *, run_time):
        """Move the dice to `band` keeping each die's slot-x (a row change)."""
        y = BAND_YS[band]
        self.play(*[d.animate.move_to([d.get_center()[0], y, 0]) for d in dice],
                  run_time=run_time)

    def _set_keep(self, dice, keep_idxs, *, run_time, dim=0.25):
        keep_idxs = set(keep_idxs)
        self.play(*[d.animate.set_opacity(1.0 if i in keep_idxs else dim)
                    for i, d in enumerate(dice)], run_time=run_time)

    def _label(self, text, x, y, *, fs=None, color=BLACK, anchor=LEFT):
        fs = self.PANEL_FS if fs is None else fs
        m = crisp_text(text, font_size=fs, color=color, font=FONT, weight="BOLD")
        m.move_to([x, y, 0], aligned_edge=anchor)
        return m

    def _count(self, specs, run_time):
        """Animate crisp_text numbers by rebuilding each frame from a ValueTracker
        (the project's LaTeX-free counter pattern, scene 13). Updaters are cleared
        so nothing unpicklable rides into the snapshot."""
        live, anims = [], []
        for s in specs:
            t = ValueTracker(s["start"])
            fmt, x, y = s["fmt"], s["x"], s["y"]
            color, anchor = s.get("color", BLACK), s.get("anchor", LEFT)

            def upd(mob, t=t, fmt=fmt, x=x, y=y, color=color, anchor=anchor):
                new = crisp_text(fmt(t.get_value()), font_size=self.PANEL_FS,
                                 color=color, font=FONT, weight="BOLD")
                new.move_to([x, y, 0], aligned_edge=anchor)
                mob.become(new)

            s["mob"].add_updater(upd)
            live.append((s, t))
            anims.append(t.animate.set_value(s["target"]))
        self.play(*anims, run_time=run_time)
        for s, t in live:
            s["mob"].clear_updaters()
            final = crisp_text(s["fmt"](s["target"]), font_size=self.PANEL_FS,
                               color=s.get("color", BLACK), font=FONT, weight="BOLD")
            final.move_to([s["x"], s["y"], 0], aligned_edge=s.get("anchor", LEFT))
            s["mob"].become(final)

    @staticmethod
    def _pct(v):
        return f"{v:.1f}%"

    @staticmethod
    def _ev(v):
        return f"{v:.2f}"

    @staticmethod
    def _keep_indices(values, keep_vec):
        """Which physical dice (left→right in `values`) make up count-vector `keep_vec`."""
        need = list(keep_vec)
        idxs = []
        for i, v in enumerate(values):
            if need[v - 1] > 0:
                idxs.append(i)
                need[v - 1] -= 1
        return idxs

    def _fly_into_box(self, dice, row, score, *, run_time=1.0):
        """Shrink the dice into a scorecard cell and fill it (geometry-agnostic
        fallback used where the fancy per-category scoring isn't needed)."""
        target = self.card.value_cells[row].get_center()
        self.play(*[d.animate.scale(0.12).move_to(target).set_opacity(0.0)
                    for d in dice], run_time=run_time * 0.55)
        self.remove(*dice)
        self.card.transition(self, {row: score}, run_time=run_time * 0.6)

    # ══════════════════════════════════════════════════════════════════════════
    # a : card fills to "all but Lg Straight"; a real turn rolls UP to 12345
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def intro_card(self, run_time=1.0):
        self.card = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        self.play(FadeIn(self.card, shift=RIGHT * 1.5), run_time=run_time)
        self.wait(0.2)
        self.card.transition(self, dict(FILL), run_time=1.4)   # fill all but Lg Str
        self.wait(0.3)

        # the standard playfield: guide lines + 5 dice staged below the bottom line
        self.board = DiceBoard()
        self.board.place_initial([2, 3, 5, 5, 1])
        self.play(FadeIn(self.board.lines),
                  *[FadeIn(d, shift=UP * 0.4) for d in self.board.dice], run_time=0.8)
        self.wait(0.3)

        # roll UP the rows toward a large straight (band 1 → 2 → 3)
        b = self.board
        self.play(*b.first_roll([1, 2, 3, 5, 5]), run_time=1.0)   # band 1
        self.wait(0.2)
        self.play(*b.keep([0, 1, 2]), run_time=0.6)               # keep 1,2,3
        self.play(*b.roll_rest([4, 6]), run_time=1.0)             # → 1,2,3,4,6 band 2
        self.wait(0.2)
        self.play(*b.keep([0, 1, 2, 3]), run_time=0.6)            # keep 1,2,3,4
        self.play(*b.roll_rest([5]), run_time=1.0)                # → 1,2,3,4,5 band 3
        self.wait(0.3)

        # "score the final dice" into the one open box (dice return to band 3)
        self.card.large_straight(self, b.dice, y=BAND_YS[3])
        self.dice = b.dice
        self.wait(0.6)

    # keep-name → physical dice indices kept (dice read 1,2,3,4,6 left→right)
    _KEEP_IDX = {"1234": [0, 1, 2, 3], "34": [2, 3], "234": [1, 2, 3], "246": [1, 3, 4]}

    # ══════════════════════════════════════════════════════════════════════════
    # b : drop to band 2 → 12346, keep 1234 (1 reroll left); odds in the row above
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def second_reroll(self, run_time=0.8):
        self.nums = dp.scene04_numbers()
        self.card.transition(self, {10: None}, run_time=0.6)      # re-open Lg Str

        # rewind one roll: dice step DOWN to band 2 and become 12346
        self._shift_band(self.dice, 2, run_time=run_time)
        morph_dice(self, self.dice, [1, 2, 3, 4, 6], run_time=0.5)
        self.wait(0.2)

        self._build_probs_panel(dice_band=2)
        self._set_keep(self.dice, [0, 1, 2, 3], run_time=0.5)     # keep 1234
        self._retarget("1234", run_time=0.9, start=0.0)
        self.wait(0.5)

    def _build_probs_panel(self, *, dice_band):
        by = BAND_YS[dice_band + 1]                # odds sit one row above the dice
        yt, yb, ym = by + 0.42, by - 0.42, by
        self.lbl_p40 = self._label("40 pts:", self.PL, yt)
        self.lbl_p0  = self._label("0 pts:",  self.PL, yb)
        self.lbl_ev  = self._label("Avg pts:", self.PR, ym)
        self.n_p40 = self._label("0.0%", self.PLN, yt)
        self.n_p0  = self._label("0.0%", self.PLN, yb)
        self.n_ev  = self._label("0.00", self.PRN, ym)
        self.panel_ys = (yt, yb, ym)
        self.play(FadeIn(VGroup(self.lbl_p40, self.lbl_p0, self.lbl_ev,
                                self.n_p40, self.n_p0, self.n_ev)), run_time=0.5)

    def _retarget(self, name, *, run_time, start=None):
        d = self.nums["second_reroll"][name]
        yt, yb, ym = self.panel_ys
        c = start
        self._count([
            {"mob": self.n_p40, "fmt": self._pct, "x": self.PLN, "y": yt,
             "start": (self.n_p40_val if c is None else c), "target": d["p40"] * 100},
            {"mob": self.n_p0,  "fmt": self._pct, "x": self.PLN, "y": yb,
             "start": (self.n_p0_val if c is None else c), "target": d["p0"] * 100},
            {"mob": self.n_ev,  "fmt": self._ev,  "x": self.PRN, "y": ym,
             "start": (self.n_ev_val if c is None else c), "target": d["ev"]},
        ], run_time)
        self.n_p40_val, self.n_p0_val, self.n_ev_val = d["p40"] * 100, d["p0"] * 100, d["ev"]

    # ══════════════════════════════════════════════════════════════════════════
    # c : cycle the kept set, counters move, back to 1234 (best → green)
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def reroll_cycle(self, run_time=0.6):
        for name in ["34", "234", "246"]:
            self._set_keep(self.dice, self._KEEP_IDX[name], run_time=run_time)
            self._retarget(name, run_time=0.8)
            self.wait(0.35)
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
        self.play(self.n_ev.animate.set_color(BLACK),
                  self.lbl_ev.animate.set_color(BLACK), run_time=0.3)
        for values in ([2, 3, 4, 5, 6], [1, 2, 3, 5, 5]):
            morph_dice(self, self.dice, values, run_time=0.5)
            for d in self.dice:
                d.set_opacity(1.0)
            keep_vec, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 1)
            self._set_keep(self.dice, self._keep_indices(values, keep_vec), run_time=run_time)
            dist = dp.score_dist_keep(None, keep_vec, dp.LARGE_STRAIGHT)
            yt, yb, ym = self.panel_ys
            self._count([
                {"mob": self.n_p40, "fmt": self._pct, "x": self.PLN, "y": yt,
                 "start": self.n_p40_val, "target": dist.get(40, 0.0) * 100},
                {"mob": self.n_p0,  "fmt": self._pct, "x": self.PLN, "y": yb,
                 "start": self.n_p0_val, "target": dist.get(0, 0.0) * 100},
                {"mob": self.n_ev,  "fmt": self._ev,  "x": self.PRN, "y": ym,
                 "start": self.n_ev_val, "target": ev},
            ], run_time=0.8)
            self.n_p40_val, self.n_p0_val, self.n_ev_val = \
                dist.get(40, 0.0) * 100, dist.get(0, 0.0) * 100, ev
            self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # e : step back to the FIRST reroll — dice to band 1, 12446, avg only, keep 24
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def first_reroll(self, run_time=0.6):
        # drop the whole probs panel; the first reroll shows AVG only
        self.play(FadeOut(VGroup(self.lbl_p40, self.lbl_p0, self.lbl_ev,
                                 self.n_p40, self.n_p0, self.n_ev)), run_time=0.4)
        # rewind another roll: dice step DOWN to band 1 and become 12446
        self._shift_band(self.dice, 1, run_time=run_time)
        morph_dice(self, self.dice, [1, 2, 4, 4, 6], run_time=0.5)
        for d in self.dice:
            d.set_opacity(1.0)

        by = BAND_YS[2]                            # avg sits one row above (band 2)
        self.lbl_ev = self._label("Avg pts:", self.PR, by)
        self.n_ev = self._label("0.00", self.PRN, by)
        self.ev_y = by
        self.play(FadeIn(VGroup(self.lbl_ev, self.n_ev)), run_time=0.4)

        keep_idx = {"124": [0, 1, 2], "24": [1, 2], "246": [1, 2, 4]}
        prev = 0.0
        for name in ["124", "24", "246", "24"]:
            self._set_keep(self.dice, keep_idx[name], run_time=run_time)
            ev = self.nums["first_reroll"][name]["ev"]
            self._count([{"mob": self.n_ev, "fmt": self._ev, "x": self.PRN,
                          "y": by, "start": prev, "target": ev}], 0.8)
            prev = ev
            self.wait(0.3)
        self.n_ev_val = prev
        self.play(self.n_ev.animate.set_color(SCORE_GREEN),
                  self.lbl_ev.animate.set_color(SCORE_GREEN), run_time=0.5)
        self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # f : a few first rolls (EV above), then dice to band 0 → one whole-turn EV
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def turn_ev(self, run_time=0.6):
        self.play(FadeOut(VGroup(self.lbl_ev, self.n_ev)), run_time=0.3)
        by = BAND_YS[2]
        above = self._label("Avg pts: 0.00", slot_x(2), by, anchor=ORIGIN)
        self.play(FadeIn(above), run_time=0.3)
        prev = 0.0
        for values in ([1, 2, 4, 4, 6], [2, 3, 4, 5, 6], [1, 1, 3, 4, 5]):
            morph_dice(self, self.dice, values, run_time=0.5)
            for d in self.dice:
                d.set_opacity(1.0)
            _, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 2)
            self._count([{"mob": above, "fmt": lambda v: f"Avg pts: {v:.2f}",
                          "x": slot_x(2), "y": by, "start": prev, "target": ev,
                          "anchor": ORIGIN}], 0.7)
            prev = ev
            self.wait(0.4)

        # "move dice back to the beginning" (band 0) and show the whole-turn EV
        self.play(FadeOut(above), run_time=0.3)
        self._shift_band(self.dice, 0, run_time=run_time)
        turn = self.nums["turn_values"]["large_straight"]
        lbl = self._label("Avg pts this turn:", slot_x(2) - 0.6, BAND_YS[1], anchor=ORIGIN)
        num = self._label("0.00", slot_x(2) + 2.3, BAND_YS[1], color=SCORE_GREEN, anchor=ORIGIN)
        self.play(FadeIn(VGroup(lbl, num)), run_time=0.4)
        self._count([{"mob": num, "fmt": self._ev, "x": slot_x(2) + 2.3, "y": BAND_YS[1],
                      "start": 0.0, "target": turn, "color": SCORE_GREEN, "anchor": ORIGIN}], 0.9)
        self.turn_lbl, self.turn_num = lbl, num
        self.wait(0.6)

    # ══════════════════════════════════════════════════════════════════════════
    # g : box choice — 11134 back at the top; compare "avg after" for two boxes
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def box_choice(self, run_time=0.6):
        self.play(FadeOut(VGroup(self.turn_lbl, self.turn_num)), run_time=0.3)
        self.turn_lbl = self.turn_num = None
        self.card.transition(self, {6: None, 7: None}, run_time=0.6)   # open 3Kind & 4Kind

        # bring the dice back to the top row (band 3) as 11134
        morph_dice(self, self.dice, [1, 1, 1, 3, 4], run_time=0.4)
        self._shift_band(self.dice, 3, run_time=run_time)
        self.wait(0.2)

        c3 = self.card.value_cells[6].get_center()
        c4 = self.card.value_cells[7].get_center()
        z3 = self._label("0", c3[0], c3[1], color=GRAY, anchor=ORIGIN)
        z4 = self._label("0", c4[0], c4[1], color=GRAY, anchor=ORIGIN)
        anchor = VGroup(*self.dice).get_bottom()
        ln3 = Line(self.card.value_cells[6].get_right(), anchor, stroke_color=GRAY, stroke_width=2.0)
        ln4 = Line(self.card.value_cells[7].get_right(), anchor, stroke_color=GRAY, stroke_width=2.0)
        self.play(FadeIn(z3), FadeIn(z4), Create(ln3), Create(ln4), run_time=0.6)

        box = self.nums["box_choice"]
        ev3, ev4 = box["fill_3kind"]["total"], box["fill_4kind"]["total"]
        lab3 = self._label(f"Avg after: {ev3:.1f}", -1.4, c3[1], anchor=LEFT)
        lab4 = self._label(f"Avg after: {ev4:.1f}", -1.4, c4[1], anchor=LEFT)
        self.play(FadeIn(lab3), FadeIn(lab4), run_time=0.5)
        self.wait(0.6)

        # NOTE (flag): the computed winner is 3-of-a-Kind (fill the 10), NOT the
        # 4-of-a-Kind the script GUESSED. Highlighting whichever wins on the numbers.
        self.play(FadeOut(VGroup(ln3, ln4, z3, z4, lab3, lab4)), run_time=0.4)
        if ev3 >= ev4:
            self.card.three_of_a_kind(self, self.dice)      # 11134 → 10 in 3-of-a-Kind
        else:
            self.card.four_of_a_kind(self, self.dice)
        self.wait(0.4)
        self.play(FadeOut(VGroup(*self.dice)), run_time=0.4)
        self.dice = None
        self.wait(0.3)

    # ══════════════════════════════════════════════════════════════════════════
    # h : (ROUGH) empty the card box-by-box; "avg points remaining" → ~255.
    #     dice sit in the top row (4th), the EV number in the row below (3rd).
    #     Intermediate values are ILLUSTRATIVE placeholders (need whole-game EVs).
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def backward_sweep(self, run_time=0.8):
        example = DiceBoard().dice          # a fresh dice row for the 4th row
        for i, (d, v) in enumerate(zip(example, [3, 3, 5, 2, 6])):
            d.set_value(v)
            d.move_to([slot_x(i), BAND_YS[3], 0])
        self.play(*[FadeIn(d) for d in example], run_time=0.5)

        lbl = self._label("Avg points remaining:", slot_x(2) - 0.4, BAND_YS[2], anchor=ORIGIN)
        num = self._label("0", slot_x(2) + 2.4, BAND_YS[2], color=SCORE_GREEN, anchor=ORIGIN)
        self.play(FadeIn(VGroup(lbl, num)), run_time=0.4)

        steps = [(12, 40), (9, 95), (8, 140), (5, 180), (2, 215), (0, 255)]
        prev = 0.0
        for box, remaining in steps:
            self.card.transition(self, {box: None}, run_time=0.5)
            self._count([{"mob": num, "fmt": lambda v: f"{v:.0f}", "x": slot_x(2) + 2.4,
                          "y": BAND_YS[2], "start": prev, "target": remaining,
                          "color": SCORE_GREEN, "anchor": ORIGIN}], 0.5)
            prev = remaining
            self.wait(0.25)
        self.wait(0.8)
