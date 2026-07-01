from pathlib import Path
import sys

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, get_die, morph_dice, slot_point, slot_x, BAND_YS
from assets import dp_data as dp


# ── the running example card: everything filled EXCEPT Large Straight ─────────
# scorecard box order: 0-5 Ones..Sixes, 6=3Kind, 7=4Kind, 8=FullHouse,
# 9=SmStraight, 10=LgStraight, 11=Yahtzee, 12=Chance, 13=Yahtzee bonus.
# A realistic near-full card: varied top section (still crosses 63 for the bonus),
# and a ZEROED Yahtzee (11 = 0) — a missed Yahtzee is strategically important.
FILL_LIST = [2, 6, 9, 12, 10, 24,          # top = 63 → bonus
             22, 24, 25, 30, None, 0, 17,  # 3K/4K/FH/SmS/(LgS open)/Yahtzee=0/Chance
             None]                          # Yahtzee bonus (n/a)

# beat h sweep: a FULL example card (scorecard order) emptied box by box.
SWEEP_FULL = {0: 3, 1: 6, 2: 9, 3: 12, 4: 15, 5: 18,
              6: 22, 7: 24, 8: 25, 9: 30, 10: 40, 11: 50, 12: 17}

GRAY = "#9A9483"          # gray placeholder "0" in an empty candidate box

# solver category (dp_data) → scorecard box index (they differ only at 11/12).
_SC_BOX = {11: 12, 12: 11}


def _sc_box(solver_cat):
    return _SC_BOX.get(solver_cat, solver_cat)


class DynamicProgramming(YahtzeeScene):
    """Scene 04 — dynamic programming: work backward from the end of the game.

    Dice live in the standard 4-band playfield (guide lines + BAND_YS). A turn's
    three rolls occupy bands 1→2→3 (rolling UP); we then walk BACKWARD, and at
    each reroll decision the KEPT dice push forward one band (the DiceBoard.keep
    convention) while the reroll odds sit to their right.

      intro_card     — card fills to "all but Lg Straight"; a real turn rolls up
                       the rows to 12345 and scores it.
      second_reroll  — 12346 at band 2; keep 1234 pushes up to band 3 (1 reroll
                       left); 40 pts / 0 pts / Avg pts to the right of the kept dice.
      reroll_cycle   — cycle the kept set (34 / 234 / 246) → back to 1234 (best).
      other_rolls    — a couple more rolls with their best keep + numbers.
      first_reroll   — 12446 at band 1; keep pushes up to band 2 (2 rerolls left);
                       Avg pts only, settle on keeping 24.
      turn_ev        — a few first rolls (EV above) → dice to band 0, one turn EV.
      box_choice     — 11134 at the top with 4-Kind & Lg Straight open; compare
                       "avg after" (zeroing 4-Kind keeps the more valuable box).
      backward_sweep — empty the card box by box while the REAL "avg points
                       remaining" (solver V) climbs to 254.6.
    """

    # ── analysis dice + odds panel ────────────────────────────────────────────
    # Dice sit in the STANDARD playfield slots (slot_x); the keep mechanic rises
    # kept dice a whole band (DiceBoard.keep). With no room for two columns to
    # their right, the odds stack VERTICALLY (40 pts / 0 pts / Avg pts), labels
    # left-aligned in one column and numbers left-aligned in another.
    LABEL_FS = 28                     # default label size
    ODDS_FS = 22
    # labels are RIGHT-anchored (colons align) at ODDS_CX; numbers LEFT-anchored
    # just after at ODDS_NX (small, consistent colon→number gap), sitting well
    # clear of the kept dice.
    ODDS_CX, ODDS_NX = 6.55, 6.68

    # ── small helpers ─────────────────────────────────────────────────────────
    def _apos(self, band, slot):
        return slot_point(band, slot)

    def _regroup(self, dice, band, *, run_time):
        """Line all five dice up in slot order at `band` (undo a keep split)."""
        self.play(*[dice[i].animate.move_to(self._apos(band, i)) for i in range(5)],
                  run_time=run_time)

    def _show_keep(self, dice, keep_idxs, base_band, *, run_time):
        """The DiceBoard.keep convention: kept dice push forward to `base_band`+1
        (left slots); the rerolled dice stay in `base_band` (the slots after the
        kept ones). Deterministic by keep-set, so it also animates keep→keep."""
        keep_set = set(keep_idxs)
        kept = [i for i in range(5) if i in keep_set]
        others = [i for i in range(5) if i not in keep_set]
        target = {}
        for s, i in enumerate(kept):
            target[i] = self._apos(base_band + 1, s)
        for j, i in enumerate(others):
            target[i] = self._apos(base_band, len(kept) + j)
        self.play(*[dice[i].animate.move_to(target[i]) for i in range(5)],
                  run_time=run_time)

    def _label(self, text, x, y, *, fs=None, color=BLACK, anchor=LEFT):
        fs = self.LABEL_FS if fs is None else fs
        m = crisp_text(text, font_size=fs, color=color, font=FONT, weight="BOLD")
        m.move_to([x, y, 0], aligned_edge=anchor)
        return m

    def _count(self, specs, run_time):
        """Animate crisp_text numbers by rebuilding each frame from a ValueTracker
        (the project's LaTeX-free counter pattern). Updaters cleared afterward."""
        live, anims = [], []
        for s in specs:
            t = ValueTracker(s["start"])
            fmt, x, y = s["fmt"], s["x"], s["y"]
            color, anchor = s.get("color", BLACK), s.get("anchor", LEFT)
            fs = s.get("fs", self.ODDS_FS)

            def upd(mob, t=t, fmt=fmt, x=x, y=y, color=color, anchor=anchor, fs=fs):
                new = crisp_text(fmt(t.get_value()), font_size=fs,
                                 color=color, font=FONT, weight="BOLD")
                new.move_to([x, y, 0], aligned_edge=anchor)
                mob.become(new)

            s["mob"].add_updater(upd)
            live.append((s, t))
            anims.append(t.animate.set_value(s["target"]))
        self.play(*anims, run_time=run_time)
        for s, t in live:
            s["mob"].clear_updaters()
            final = crisp_text(s["fmt"](s["target"]), font_size=s.get("fs", self.ODDS_FS),
                               color=s.get("color", BLACK), font=FONT, weight="BOLD")
            final.move_to([s["x"], s["y"], 0], aligned_edge=s.get("anchor", LEFT))
            s["mob"].become(final)

    @staticmethod
    def _pct(v):
        return f"{v:.0f}%"

    @staticmethod
    def _ev(v):
        return f"{v:.2f}"

    @staticmethod
    def _keep_indices(values, keep_vec):
        need = list(keep_vec)
        idxs = []
        for i, v in enumerate(values):
            if need[v - 1] > 0:
                idxs.append(i)
                need[v - 1] -= 1
        return idxs

    # ══════════════════════════════════════════════════════════════════════════
    # a : card fills to "all but Lg Straight"; a real turn rolls UP to 12345
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def intro_card(self, run_time=1.0):
        # The near-full card fades in ALREADY filled (so the top-bonus bar never
        # animates up), together with the dice dropping in from the TOP — no roll
        # sequence. dice 12345 are staged at the top row; Lg Straight is open.
        self.card = get_scorecard(center=LEFT_SC, scores=list(FILL_LIST))
        self.board = DiceBoard()
        for i, d in enumerate(self.board.dice):
            d.set_value([1, 2, 3, 4, 5][i])
            d.move_to(slot_point(3, i))
        self.play(FadeIn(self.card, shift=RIGHT * 1.5),
                  FadeIn(self.board.lines),
                  *[FadeIn(d, shift=DOWN * 0.7) for d in self.board.dice],
                  run_time=run_time)
        self.wait(0.3)

        self.card.large_straight(self, self.board.dice, y=BAND_YS[3])   # score the final dice
        self.dice = self.board.dice
        self.wait(0.6)

    # keep-name → dice indices (dice read 1,2,3,4,6 left→right after the regroup)
    _KEEP_IDX = {"1234": [0, 1, 2, 3], "34": [2, 3], "234": [1, 2, 3], "246": [1, 3, 4]}

    # ══════════════════════════════════════════════════════════════════════════
    # b : 12346 at band 2; keep 1234 pushes up to band 3; odds to the right
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def second_reroll(self, run_time=0.8):
        self.nums = dp.scene04_numbers()
        self.card.transition(self, {10: None}, run_time=0.6)      # re-open Lg Str

        self._regroup(self.dice, 2, run_time=run_time)            # drop to band 2
        morph_dice(self, self.dice, [1, 2, 3, 4, 6], run_time=0.5)
        self.wait(0.2)

        self._build_probs_panel(base_band=2)
        self._show_keep(self.dice, [0, 1, 2, 3], base_band=2, run_time=0.6)  # keep 1234
        self.play(FadeIn(VGroup(self.lbl_p40, self.lbl_p0, self.lbl_ev,
                                self.n_p40, self.n_p0, self.n_ev)), run_time=0.4)
        self._retarget("1234", run_time=0.9, start=0.0)
        self.wait(0.5)

    def _panel_ys(self, base_band):
        """The three stacked rows (40 / 0 / Avg) beside the kept dice, which sit in
        band `base_band`+1."""
        by = BAND_YS[base_band + 1]
        return by + 0.5, by, by - 0.5

    # the whole-turn EV lands in the MIDDLE of the 3rd row (band 1), bigger.
    TURN_FS = 40
    TURN_CX, TURN_NX = 3.45, 3.60

    def _land_turn_ev(self, dice, lbl, num, prev, *, run_time):
        """Move `dice` down to the bottom row (band 0) and, AT THE SAME TIME, the
        Avg pts (lbl+num) down to the centre of the 3rd row (band 1), enlarged;
        then count the number to the whole-turn EV. Shared by f and the montage."""
        big_lbl = self._label("Avg pts:", self.TURN_CX, BAND_YS[1], fs=self.TURN_FS, anchor=RIGHT)
        self.play(
            *[dice[i].animate.move_to(slot_point(0, i)) for i in range(5)],
            Transform(lbl, big_lbl),
            num.animate.scale(self.TURN_FS / self.ODDS_FS).move_to(
                [self.TURN_NX, BAND_YS[1], 0], aligned_edge=LEFT),
            run_time=run_time,
        )
        turn = self.nums["turn_values"]["large_straight"]
        self._count([{"mob": num, "fmt": self._ev, "x": self.TURN_NX, "y": BAND_YS[1],
                      "start": prev, "target": turn, "color": SCORE_GREEN, "fs": self.TURN_FS}], 0.9)

    def _build_probs_panel(self, base_band):
        yt, ym, yb = self._panel_ys(base_band)
        self._num_pos = {"p40": (self.ODDS_NX, yt), "p0": (self.ODDS_NX, ym),
                         "ev": (self.ODDS_NX, yb)}
        self.lbl_p40 = self._label("40 pts:", self.ODDS_CX, yt, fs=self.ODDS_FS, anchor=RIGHT)
        self.lbl_p0  = self._label("0 pts:",  self.ODDS_CX, ym, fs=self.ODDS_FS, anchor=RIGHT)
        self.lbl_ev  = self._label("Avg pts:", self.ODDS_CX, yb, fs=self.ODDS_FS, anchor=RIGHT)
        self.n_p40 = self._label("0%", self.ODDS_NX, yt, fs=self.ODDS_FS)
        self.n_p0  = self._label("0%", self.ODDS_NX, ym, fs=self.ODDS_FS)
        self.n_ev  = self._label("0.00", self.ODDS_NX, yb, fs=self.ODDS_FS)

    def _retarget(self, name, *, run_time, start=None):
        d = self.nums["second_reroll"][name]
        c = start
        specs = []
        for key, mob, fmt, tgt, cur in (
            ("p40", self.n_p40, self._pct, d["p40"] * 100, getattr(self, "n_p40_val", 0.0)),
            ("p0",  self.n_p0,  self._pct, d["p0"] * 100,  getattr(self, "n_p0_val", 0.0)),
            ("ev",  self.n_ev,  self._ev,  d["ev"],        getattr(self, "n_ev_val", 0.0)),
        ):
            x, y = self._num_pos[key]
            specs.append({"mob": mob, "fmt": fmt, "x": x, "y": y, "fs": self.ODDS_FS,
                          "start": (cur if c is None else c), "target": tgt})
        self._count(specs, run_time)
        self.n_p40_val, self.n_p0_val, self.n_ev_val = d["p40"] * 100, d["p0"] * 100, d["ev"]

    # ══════════════════════════════════════════════════════════════════════════
    # c : cycle the kept set (dice re-rise each time), back to 1234 (best → green)
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def reroll_cycle(self, run_time=0.6):
        for name in ["34", "234", "246"]:
            self._show_keep(self.dice, self._KEEP_IDX[name], base_band=2, run_time=run_time)
            self._retarget(name, run_time=0.8)
            self.wait(0.35)
        self._show_keep(self.dice, self._KEEP_IDX["1234"], base_band=2, run_time=run_time)
        self._retarget("1234", run_time=0.8)
        self.play(self.n_ev.animate.set_color(SCORE_GREEN), run_time=0.5)  # number only
        self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # d : a couple more rolls with their best keep + numbers already in place
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def other_rolls(self, run_time=0.6):
        # the Avg number stays GREEN for these (best-keep) examples (number only)
        # script: "3 other dice configurations with their best dice combos forward"
        # — varied, and NOT all four-dice keeps (4 / 3 / 2 kept respectively).
        for values in ([1, 2, 4, 4, 5], [3, 3, 4, 5, 5], [1, 1, 1, 2, 3]):
            self._regroup(self.dice, 2, run_time=0.5)
            morph_dice(self, self.dice, values, run_time=0.5)
            keep_vec, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 1)
            self._show_keep(self.dice, self._keep_indices(values, keep_vec),
                            base_band=2, run_time=run_time)
            dist = dp.score_dist_keep(None, keep_vec, dp.LARGE_STRAIGHT)
            p40, p0 = dist.get(40, 0.0) * 100, dist.get(0, 0.0) * 100
            (x40, y40), (x0, y0), (xev, yev) = (self._num_pos["p40"],
                                                self._num_pos["p0"], self._num_pos["ev"])
            self._count([
                {"mob": self.n_p40, "fmt": self._pct, "x": x40, "y": y40, "fs": self.ODDS_FS,
                 "start": self.n_p40_val, "target": p40},
                {"mob": self.n_p0,  "fmt": self._pct, "x": x0, "y": y0, "fs": self.ODDS_FS,
                 "start": self.n_p0_val, "target": p0},
                {"mob": self.n_ev,  "fmt": self._ev,  "x": xev, "y": yev, "fs": self.ODDS_FS,
                 "color": SCORE_GREEN, "start": self.n_ev_val, "target": ev},
            ], run_time=0.8)
            self.n_p40_val, self.n_p0_val, self.n_ev_val = p40, p0, ev
            self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # e : step back to the FIRST reroll — 12446 at band 1, keep 24 (avg only)
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def first_reroll(self, run_time=0.6):
        self.play(FadeOut(VGroup(self.lbl_p40, self.lbl_p0, self.n_p40, self.n_p0)),
                  run_time=0.4)                                    # avg only now
        self._regroup(self.dice, 1, run_time=run_time)            # drop to band 1
        morph_dice(self, self.dice, [1, 2, 4, 4, 6], run_time=0.5)
        # the Avg label + number GLIDE to band 2 (label right-anchored, number
        # left-anchored → they stay vertically aligned); number back to black.
        by = BAND_YS[2]
        self.play(self.lbl_ev.animate.move_to([self.ODDS_CX, by, 0], aligned_edge=RIGHT),
                  self.n_ev.animate.set_color(BLACK).move_to([self.ODDS_NX, by, 0], aligned_edge=LEFT),
                  run_time=0.5)
        self.ev_y = by

        keep_idx = {"124": [0, 1, 2], "24": [1, 2], "246": [1, 2, 4]}
        prev = self.n_ev_val
        for name in ["124", "24", "246", "24"]:
            self._show_keep(self.dice, keep_idx[name], base_band=1, run_time=run_time)
            ev = self.nums["first_reroll"][name]["ev"]
            self._count([{"mob": self.n_ev, "fmt": self._ev, "x": self.ODDS_NX,
                          "y": by, "start": prev, "target": ev, "fs": self.ODDS_FS}], 0.8)
            prev = ev
            self.wait(0.3)
        self.n_ev_val = prev
        self.play(self.n_ev.animate.set_color(SCORE_GREEN), run_time=0.5)  # number only
        self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # f : a few first rolls (EV above), then dice to band 0 → one whole-turn EV
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def turn_ev(self, run_time=0.6):
        # FIRST PART like d: each first roll's best keep is SET FORWARD, with its
        # Avg pts (green number) — reusing the same panel label/number from e.
        by = BAND_YS[2]
        prev = self.n_ev_val
        for values in ([1, 2, 4, 4, 6], [2, 3, 5, 5, 6], [1, 1, 3, 4, 5]):
            self._regroup(self.dice, 1, run_time=0.4)
            morph_dice(self, self.dice, values, run_time=0.5)
            keep_vec, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 2)
            self._show_keep(self.dice, self._keep_indices(values, keep_vec),
                            base_band=1, run_time=run_time)
            self._count([{"mob": self.n_ev, "fmt": self._ev, "x": self.ODDS_NX, "y": by,
                          "start": prev, "target": ev, "color": SCORE_GREEN,
                          "fs": self.ODDS_FS}], 0.7)
            prev = ev
            self.wait(0.4)

        # END: dice to the beginning (band 0) + Avg pts to the middle of the 3rd
        # row, bigger, its number becoming the whole-turn EV (text stays "Avg pts:").
        self._land_turn_ev(self.dice, self.lbl_ev, self.n_ev, prev, run_time=run_time)
        self.turn_lbl, self.turn_num = self.lbl_ev, self.n_ev
        self.wait(0.6)

    # ══════════════════════════════════════════════════════════════════════════
    # g : box choice — 11134 with 4-Kind & Lg Straight open; compare "avg after"
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def box_choice(self, run_time=0.6):
        self.play(FadeOut(VGroup(self.turn_lbl, self.turn_num)), run_time=0.3)
        self.turn_lbl = self.turn_num = None
        # open 4-of-a-Kind (Lg Straight is already open from the running example);
        # 3-of-a-Kind stays filled.
        self.card.transition(self, {7: None, 10: None}, run_time=0.6)

        morph_dice(self, self.dice, [1, 1, 1, 3, 4], run_time=0.4)
        self._regroup(self.dice, 3, run_time=run_time)            # up to the top row
        self.wait(0.2)

        c4 = self.card.value_cells[7].get_center()                # 4-of-a-Kind
        cls = self.card.value_cells[10].get_center()              # Lg Straight
        z4 = self._label("0", c4[0], c4[1], color=GRAY, anchor=ORIGIN)
        zls = self._label("0", cls[0], cls[1], color=GRAY, anchor=ORIGIN)
        # HORIZONTAL arrows from the card's right edge (level with each box) out
        # into the open area; the Avg-after EV sits at the far (right) end of each.
        card_rx = self.card.get_right()[0] + 0.05
        head_x = 2.1
        ar4 = Arrow([card_rx, c4[1], 0], [head_x, c4[1], 0], color=BLACK,
                    buff=0, stroke_width=3.5, max_tip_length_to_length_ratio=0.06)
        arls = Arrow([card_rx, cls[1], 0], [head_x, cls[1], 0], color=BLACK,
                     buff=0, stroke_width=3.5, max_tip_length_to_length_ratio=0.06)
        self.play(FadeIn(z4), FadeIn(zls), GrowArrow(ar4), GrowArrow(arls), run_time=0.6)
        self.wait(0.8)                                             # beat before the EVs

        box = self.nums["box_choice"]
        ev4 = box["fill_4kind"]["total"]          # zero 4-Kind, keep Lg Straight open
        evls = box["fill_lgstraight"]["total"]    # zero Lg Straight, keep 4-Kind open
        lab4 = self._label(f"Avg points after: {ev4:.1f}", head_x + 0.25, c4[1], anchor=LEFT, fs=24)
        labls = self._label(f"Avg points after: {evls:.1f}", head_x + 0.25, cls[1], anchor=LEFT, fs=24)
        self.play(FadeIn(lab4), FadeIn(labls), run_time=0.5)
        self.wait(0.6)

        # zero out the LOWER-EV box (keep the higher-value one open) → the 4-Kind
        self.play(FadeOut(VGroup(ar4, arls, z4, zls, lab4, labls)), run_time=0.4)
        zero_row = 7 if ev4 >= evls else 10
        self.card.animate_zero_score(self, zero_row, self.dice)
        self.wait(0.4)
        self.play(FadeOut(VGroup(*self.dice)), run_time=0.4)
        self.dice = None
        self.wait(0.3)

    # ══════════════════════════════════════════════════════════════════════════
    # h : the backward-induction montage — like d/e, repeated GOING DOWN the rows
    #     (rows count from the top). Full-size dice; the optimal keep is SET FORWARD
    #     (rises a band); the EV sits above-right (in the row above the base dice).
    #     Row 2 dice → EV row 1; then row 3 dice → EV row 2; then the whole-turn EV
    #     at the bottom (row 4). Going backwards, so 4-of-a-Kind is unfilled.
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def keep_montage(self, run_time=0.6):
        self.card.transition(self, {7: None}, run_time=0.6)       # 4-Kind unfilled again
        dice = [get_die(1) for _ in range(5)]                     # same size as always

        # the EV panel (Avg pts: <green number>), right of the kept dice, one row up
        ev_lbl = self._label("Avg pts:", self.ODDS_CX, BAND_YS[3], fs=self.ODDS_FS, anchor=RIGHT)
        ev_num = self._label("0.00", self.ODDS_NX, BAND_YS[3], color=SCORE_GREEN, fs=self.ODDS_FS)
        for s, d in enumerate(dice):                              # reveal in row 2 (band 2)
            d.set_value([1, 2, 4, 4, 6][s])
            d.move_to(slot_point(2, s))
        self.play(*[FadeIn(d) for d in dice], FadeIn(ev_lbl), FadeIn(ev_num), run_time=0.5)

        prev = [0.0]

        def _roll(values, base_band, ev_band, *, move_avg=False):
            keep_vec, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 2)
            # flatten the dice at `base_band`; on a row change, the avg moves down
            # to `ev_band` AT THE SAME TIME (not first).
            anims = [dice[i].animate.move_to(slot_point(base_band, i)) for i in range(5)]
            if move_avg:
                anims += [ev_lbl.animate.move_to([self.ODDS_CX, BAND_YS[ev_band], 0], aligned_edge=RIGHT),
                          ev_num.animate.move_to([self.ODDS_NX, BAND_YS[ev_band], 0], aligned_edge=LEFT)]
            self.play(*anims, run_time=0.4)
            morph_dice(self, dice, values, run_time=0.4)
            self._show_keep(dice, self._keep_indices(values, keep_vec),
                            base_band=base_band, run_time=run_time)          # SET FORWARD
            self._count([{"mob": ev_num, "fmt": self._ev, "x": self.ODDS_NX,
                          "y": BAND_YS[ev_band], "start": prev[0], "target": ev,
                          "color": SCORE_GREEN, "fs": self.ODDS_FS}], 0.5)
            prev[0] = ev
            self.wait(0.25)

        # row 2 dice (band 2), EV in row 1 (band 3, above)
        _roll([1, 2, 4, 4, 6], 2, 3)
        _roll([2, 3, 5, 5, 6], 2, 3)
        # go DOWN together — dice to row 3 (band 1), EV to row 2 (band 2)
        _roll([1, 2, 3, 5, 5], 1, 2, move_avg=True)
        _roll([2, 4, 4, 5, 6], 1, 2)

        # end like f: dice down to the bottom row + avg to the middle of the 3rd
        # row (bigger), together, its number becoming the whole-turn EV.
        self._land_turn_ev(dice, ev_lbl, ev_num, prev[0], run_time=run_time)
        self.wait(0.8)
        self.play(FadeOut(VGroup(*dice, ev_lbl, ev_num)), run_time=0.4)   # clear before the sweep
        self.wait(0.2)

    # ══════════════════════════════════════════════════════════════════════════
    # i : empty the card box-by-box; REAL "avg points remaining" (solver V) → 254.6
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def backward_sweep(self, run_time=0.8):
        # reset the card to a full example card; the dice stay at the BOTTOM (band 0)
        # for all of this subscene, and the running EV sits in the 3rd row (band 2).
        self.card.transition(self, dict(SWEEP_FULL), run_time=0.8)
        example = DiceBoard().dice
        for i, (d, v) in enumerate(zip(example, [3, 3, 5, 2, 6])):
            d.set_value(v)
            d.move_to([slot_x(i), BAND_YS[0], 0])
        self.play(*[FadeIn(d) for d in example], run_time=0.5)

        by = BAND_YS[1]                          # the EV lives in the 3rd row (top-down)
        onedp = lambda v: f"{v:.1f}"             # real solver V, to one decimal
        lbl = self._label("Avg points remaining:", slot_x(2) - 0.6, by, anchor=ORIGIN, fs=32)
        num = self._label("0.0", slot_x(2) + 2.7, by, color=SCORE_GREEN, anchor=ORIGIN, fs=32)
        self.play(FadeIn(VGroup(lbl, num)), run_time=0.4)

        seq = self.nums["sweep"]                 # real solver V at each step
        prev = seq[0]["remaining"]
        self._count([{"mob": num, "fmt": onedp, "x": slot_x(2) + 2.7,
                      "y": by, "start": 0.0, "target": prev, "color": SCORE_GREEN,
                      "anchor": ORIGIN, "fs": 32}], 0.4)
        for step in seq[1:]:
            self.card.transition(self, {_sc_box(step["emptied"]): None}, run_time=0.45)
            self._count([{"mob": num, "fmt": onedp, "x": slot_x(2) + 2.7,
                          "y": by, "start": prev, "target": step["remaining"],
                          "color": SCORE_GREEN, "anchor": ORIGIN, "fs": 32}], 0.4)
            prev = step["remaining"]
            self.wait(0.15)
        self.wait(0.8)
