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
FILL = {0: 3, 1: 6, 2: 9, 3: 12, 4: 15, 5: 18,   # top = 63 → bonus earned
        6: 22, 7: 24, 8: 25, 9: 30, 11: 50, 12: 17}  # (10 = Lg Straight open)

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
    ODDS_LX, ODDS_NX = 5.05, 6.60     # odds labels / numbers (right of kept dice)

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
        return f"{v:.1f}%"

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
        self.card = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        # dice 12345 already at the TOP row (no roll sequence); they drop in from
        # above (shift DOWN) together with the empty card + guide lines.
        self.board = DiceBoard()
        for i, d in enumerate(self.board.dice):
            d.set_value([1, 2, 3, 4, 5][i])
            d.move_to(slot_point(3, i))
        self.play(FadeIn(self.card, shift=RIGHT * 1.5),
                  FadeIn(self.board.lines),
                  *[FadeIn(d, shift=DOWN * 0.7) for d in self.board.dice],
                  run_time=run_time)
        self.wait(0.2)
        # a plain transition from empty → "all but Lg Straight" (no box-by-box
        # scoring). NB: card.transition runs as its own play, so this reads as
        # "dice arrive from the top, THEN the card fills" — to overlap the fill
        # with the dice exactly would need composing with the card's animator.
        self.card.transition(self, dict(FILL), run_time=1.4)
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

    def _build_probs_panel(self, base_band):
        yt, ym, yb = self._panel_ys(base_band)
        self._num_pos = {"p40": (self.ODDS_NX, yt), "p0": (self.ODDS_NX, ym),
                         "ev": (self.ODDS_NX, yb)}
        self.lbl_p40 = self._label("40 pts:", self.ODDS_LX, yt, fs=self.ODDS_FS)
        self.lbl_p0  = self._label("0 pts:",  self.ODDS_LX, ym, fs=self.ODDS_FS)
        self.lbl_ev  = self._label("Avg pts:", self.ODDS_LX, yb, fs=self.ODDS_FS)
        self.n_p40 = self._label("0.0%", self.ODDS_NX, yt, fs=self.ODDS_FS)
        self.n_p0  = self._label("0.0%", self.ODDS_NX, ym, fs=self.ODDS_FS)
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
                 "start": self.n_ev_val, "target": ev},
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
        # the Avg label+number GLIDE (not jump) down beside band 2 (the kept row)
        by = BAND_YS[2]
        self.play(self.lbl_ev.animate.move_to([self.ODDS_LX, by, 0], aligned_edge=LEFT),
                  self.n_ev.animate.move_to([self.ODDS_NX, by, 0], aligned_edge=LEFT),
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
        self.play(self.n_ev.animate.set_color(SCORE_GREEN),
                  self.lbl_ev.animate.set_color(SCORE_GREEN), run_time=0.5)
        self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # f : a few first rolls (EV above), then dice to band 0 → one whole-turn EV
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def turn_ev(self, run_time=0.6):
        # reuse the SAME "Avg pts:" label + number carried from the first reroll —
        # it only ever MOVES and its number changes; the text is never recreated.
        by = BAND_YS[2]
        cx_lbl, cx_num = 1.6, 3.4                 # centred above the band-1 dice
        self.play(self.lbl_ev.animate.set_color(BLACK).move_to([cx_lbl, by, 0], aligned_edge=LEFT),
                  self.n_ev.animate.set_color(BLACK).move_to([cx_num, by, 0], aligned_edge=LEFT),
                  run_time=0.5)
        prev = self.n_ev_val
        for values in ([1, 2, 4, 4, 6], [2, 3, 4, 5, 6], [1, 1, 3, 4, 5]):
            self._regroup(self.dice, 1, run_time=0.4)
            morph_dice(self, self.dice, values, run_time=0.5)
            _, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 2)
            self._count([{"mob": self.n_ev, "fmt": self._ev, "x": cx_num, "y": by,
                          "start": prev, "target": ev, "fs": self.ODDS_FS}], 0.7)
            prev = ev
            self.wait(0.4)

        # move dice back to the beginning (band 0); the Avg pts moves ONE more time
        # and its number becomes the whole-turn EV — the "Avg pts:" text stays.
        turn = self.nums["turn_values"]["large_straight"]
        by1 = BAND_YS[1]
        self.play(
            *[self.dice[i].animate.move_to(slot_point(0, i)) for i in range(5)],
            self.lbl_ev.animate.move_to([cx_lbl, by1, 0], aligned_edge=LEFT),
            self.n_ev.animate.set_color(SCORE_GREEN).move_to([cx_num, by1, 0], aligned_edge=LEFT),
            run_time=run_time,
        )
        self._count([{"mob": self.n_ev, "fmt": self._ev, "x": cx_num, "y": by1,
                      "start": prev, "target": turn, "color": SCORE_GREEN, "fs": self.ODDS_FS}], 0.9)
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
        # lines start at the card's RIGHT EDGE (level with each box) so they aren't
        # occluded by the card, and run OUT to the dice.
        card_rx = self.card.get_right()[0] + 0.05
        anchor = VGroup(*self.dice).get_bottom()
        s4 = np.array([card_rx, c4[1], 0.0])
        sls = np.array([card_rx, cls[1], 0.0])
        ln4 = Line(s4, anchor, stroke_color=GRAY, stroke_width=2.0)
        lnls = Line(sls, anchor, stroke_color=GRAY, stroke_width=2.0)
        self.play(FadeIn(z4), FadeIn(zls), Create(ln4), Create(lnls), run_time=0.6)
        self.wait(0.7)                                             # beat before the EVs

        box = self.nums["box_choice"]
        ev4 = box["fill_4kind"]["total"]          # zero 4-Kind, keep Lg Straight open
        evls = box["fill_lgstraight"]["total"]    # zero Lg Straight, keep 4-Kind open
        # EVs sit ON their lines (different points, so they don't collide)
        p4 = s4 + 0.35 * (anchor - s4)
        pls = sls + 0.18 * (anchor - sls)
        lab4 = self._label(f"Avg points after: {ev4:.1f}", p4[0], p4[1], anchor=LEFT, fs=24)
        labls = self._label(f"Avg points after: {evls:.1f}", pls[0], pls[1], anchor=LEFT, fs=24)
        self.play(FadeIn(lab4), FadeIn(labls), run_time=0.5)
        self.wait(0.6)

        # zero out the LOWER-EV box (keep the higher-value one open) → the 4-Kind
        self.play(FadeOut(VGroup(ln4, lnls, z4, zls, lab4, labls)), run_time=0.4)
        zero_row = 7 if ev4 >= evls else 10
        self.card.animate_zero_score(self, zero_row, self.dice)
        self.wait(0.4)
        self.play(FadeOut(VGroup(*self.dice)), run_time=0.4)
        self.dice = None
        self.wait(0.3)

    # ══════════════════════════════════════════════════════════════════════════
    # h : (ROUGH) the backward-induction montage. Going backwards, so 4-of-a-Kind
    #     is unfilled again. Various dice arrangements cycle in the SECOND row with
    #     their EV in the FIRST row; then in the THIRD row with the EV in the
    #     SECOND row; then the whole-turn EV at the bottom. EVs are the real
    #     Large-Straight best-keep (2-reroll) values.
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def keep_montage(self, run_time=0.6):
        self.card.transition(self, {7: None}, run_time=0.6)       # 4-Kind unfilled again
        dice = [get_die(1, size=0.72) for _ in range(5)]
        EV_LX, EV_NX = 2.35, 3.15

        def _forward(values, dice_band, *, run_time):
            keep_vec, ev = dp.best_keep(dp.values_to_vec(values), dp.LARGE_STRAIGHT, 2)
            keep = set(self._keep_indices(values, keep_vec))
            morph_dice(self, dice, values, run_time=run_time * 0.6)
            self.play(*[dice[s].animate.move_to(                  # optimal dice set FORWARD
                        [slot_x(s), BAND_YS[dice_band] + (0.3 if s in keep else 0.0), 0])
                        for s in range(5)], run_time=run_time)
            return ev

        # place the first arrangement in the SECOND row (band 1) without a play,
        # then reveal dice + the EV in the FIRST row (band 0)
        v0 = [1, 2, 4, 4, 6]
        kv0, ev = dp.best_keep(dp.values_to_vec(v0), dp.LARGE_STRAIGHT, 2)
        keep0 = set(self._keep_indices(v0, kv0))
        for s, d in enumerate(dice):
            d.set_value(v0[s])
            d.move_to([slot_x(s), BAND_YS[1] + (0.3 if s in keep0 else 0.0), 0])
        ev_lbl = self._label("EV:", EV_LX, BAND_YS[0], fs=28)
        ev_num = self._label(self._ev(ev), EV_NX, BAND_YS[0], color=SCORE_GREEN, fs=28)
        self.play(*[FadeIn(d) for d in dice], FadeIn(ev_lbl), FadeIn(ev_num), run_time=0.5)
        self.wait(0.3)

        def _cycle(rolls, dice_band, ev_band, prev):
            for values in rolls:
                ev = _forward(values, dice_band, run_time=run_time)
                self._count([{"mob": ev_num, "fmt": self._ev, "x": EV_NX,
                              "y": BAND_YS[ev_band], "start": prev, "target": ev,
                              "color": SCORE_GREEN, "fs": 28}], 0.6)
                prev = ev
                self.wait(0.3)
            return prev

        prev = _cycle([[2, 2, 3, 5, 6], [1, 3, 4, 4, 5]], 1, 0, ev)   # second row / first row

        # dice climb to the THIRD row (band 2), EV climbs to the SECOND row (band 1)
        self.play(ev_lbl.animate.move_to([EV_LX, BAND_YS[1], 0], aligned_edge=LEFT),
                  ev_num.animate.move_to([EV_NX, BAND_YS[1], 0], aligned_edge=LEFT),
                  run_time=0.4)
        prev = _cycle([[1, 2, 3, 5, 5], [2, 4, 4, 5, 6]], 2, 1, prev)  # third row / second row

        # the whole-turn EV, at the bottom
        turn = self.nums["turn_values"]["large_straight"]
        self.play(FadeOut(VGroup(*dice)),
                  ev_lbl.animate.move_to([EV_LX, BAND_YS[0], 0], aligned_edge=LEFT),
                  ev_num.animate.move_to([EV_NX, BAND_YS[0], 0], aligned_edge=LEFT),
                  run_time=0.5)
        self._count([{"mob": ev_num, "fmt": self._ev, "x": EV_NX, "y": BAND_YS[0],
                      "start": prev, "target": turn, "color": SCORE_GREEN, "fs": 28}], 0.6)
        self.wait(0.8)

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

        by = BAND_YS[2]                          # the EV number lives in the "3rd row"
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
