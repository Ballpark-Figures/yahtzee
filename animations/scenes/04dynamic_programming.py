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
    # digit-only numbers sit a hair LOW next to their labels, because a label like
    # "Avg pts:" has descenders (the p) that stretch its bounding box down and so
    # raise its centre; the number has none. Nudge every number UP by this fraction
    # of its font size so its baseline lands on the label's baseline (measured, and
    # constant across font sizes).
    NUM_BASELINE_DY = 0.00136

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

    def _label(self, text, x, y, *, fs=None, color=BLACK, anchor=LEFT, dy=0.0):
        fs = self.LABEL_FS if fs is None else fs
        m = crisp_text(text, font_size=fs, color=color, font=FONT, weight="BOLD")
        m.move_to([x, y + dy, 0], aligned_edge=anchor)
        return m

    def _ny(self, y, fs):
        """`y` nudged UP so a digit-only number's baseline matches its label's."""
        return y + self.NUM_BASELINE_DY * fs

    def _numlabel(self, text, x, y, *, fs, color=BLACK, anchor=LEFT):
        """Like `_label` but for a NUMBER — applies the baseline nudge."""
        return self._label(text, x, y, fs=fs, color=color, anchor=anchor,
                           dy=self.NUM_BASELINE_DY * fs)

    def _remaining_label(self, x, y, fs):
        """A 2-line right-anchored "Avg points / remaining:" label centred at
        (x, y) — used where the full phrase is too wide for one line (h's right
        column). Returns (group, line2_dy): the y-offset of the "remaining:" line
        from the group centre, so a number can sit ON that line."""
        l1 = crisp_text("Avg points", font_size=fs, color=BLACK, font=FONT, weight="BOLD")
        l2 = crisp_text("remaining:", font_size=fs, color=BLACK, font=FONT, weight="BOLD")
        g = VGroup(l1, l2).arrange(DOWN, buff=0.06, aligned_edge=RIGHT)
        g.move_to([x, y, 0], aligned_edge=RIGHT)
        return g, l2.get_center()[1] - g.get_center()[1]

    def _count(self, specs, run_time):
        """Animate crisp_text numbers by rebuilding each frame from a ValueTracker
        (the project's LaTeX-free counter pattern). Updaters cleared afterward."""
        live, anims = [], []
        for s in specs:
            t = ValueTracker(s["start"])
            fmt, x = s["fmt"], s["x"]
            color, anchor = s.get("color", BLACK), s.get("anchor", LEFT)
            fs = s.get("fs", self.ODDS_FS)
            y = self._ny(s["y"], fs)            # baseline nudge (numbers only)

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
            fs = s.get("fs", self.ODDS_FS)
            final = crisp_text(s["fmt"](s["target"]), font_size=fs,
                               color=s.get("color", BLACK), font=FONT, weight="BOLD")
            final.move_to([s["x"], self._ny(s["y"], fs), 0], aligned_edge=s.get("anchor", LEFT))
            s["mob"].become(final)

    @staticmethod
    def _pct(v):
        return f"{v:.0f}%"

    @staticmethod
    def _ev(v):
        return f"{v:.2f}"

    @staticmethod
    def _onedp(v):
        return f"{v:.1f}"

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
    def intro_card(self):
        run_time = 1.0
        # Three separate script beats, in order, with delays between (matching the
        # script's paragraph breaks): 1. empty scorecard comes on, 2. dice come on
        # (from the TOP), 3. the card fills out. The fill is a full filled card
        # FADED IN over the empty one, so the values + bar appear at their FINAL
        # state — the bar never grows.
        empty = get_scorecard(center=LEFT_SC, scores=[None] * 14)
        self.card = get_scorecard(center=LEFT_SC, scores=list(FILL_LIST))
        self.board = DiceBoard()
        for i, d in enumerate(self.board.dice):
            d.set_value([1, 2, 3, 4, 5][i])
            d.move_to(slot_point(3, i))

        self.play(FadeIn(empty, shift=RIGHT * 1.5), run_time=run_time)     # 1. empty card
        self.wait(0.7)
        self.play(FadeIn(self.board.lines),                               # 2. dice from top
                  *[FadeIn(d, shift=DOWN * 0.7) for d in self.board.dice], run_time=0.8)
        self.wait(0.7)
        self.add(self.card)                                               # 3. fill (no bar grow)
        self.play(FadeIn(self.card), run_time=1.0)
        self.remove(empty)
        self.wait(0.3)

        self.card.large_straight(self, self.board.dice, y=BAND_YS[3])     # score the final dice
        self.dice = self.board.dice

    # keep-name → dice indices (dice read 1,2,3,4,6 left→right after the regroup)
    _KEEP_IDX = {"1234": [0, 1, 2, 3], "34": [2, 3], "234": [1, 2, 3], "246": [1, 3, 4]}

    # ══════════════════════════════════════════════════════════════════════════
    # b : 12346 at band 2; keep 1234 pushes up to band 3; odds to the right
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def second_reroll(self):
        run_time = 0.8
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

    def _panel_ys(self, base_band):
        """The three stacked rows (40 / 0 / Avg) beside the kept dice, which sit in
        band `base_band`+1."""
        by = BAND_YS[base_band + 1]
        return by + 0.5, by, by - 0.5

    # the whole-turn EV lands in the MIDDLE of the 3rd row (band 1), bigger.
    TURN_FS = 40
    TURN_CX, TURN_NX = 3.45, 3.60

    def _land_turn_ev(self, dice, lbl, num, prev, turn, *, run_time, label="Avg pts:",
                      fs=None, lbl_x=None, num_x=None, anchor_lbl=RIGHT, anchor_num=LEFT,
                      fmt=None):
        """Move `dice` down to the bottom row (band 0) and, AT THE SAME TIME, the
        avg-points (lbl+num) down to the 3rd row (band 1); then count the number to
        the whole-turn EV `turn`. Defaults land it BIG and central (beat f); h passes
        beat i's smaller layout so the value doesn't jump size/position at the hand-off."""
        fs = self.TURN_FS if fs is None else fs
        lbl_x = self.TURN_CX if lbl_x is None else lbl_x
        num_x = self.TURN_NX if num_x is None else num_x
        fmt = self._ev if fmt is None else fmt
        y = BAND_YS[1]
        big_lbl = self._label(label, lbl_x, y, fs=fs, anchor=anchor_lbl)
        self.play(
            *[dice[i].animate.move_to(slot_point(0, i)) for i in range(5)],
            Transform(lbl, big_lbl),
            num.animate.scale(fs / self.ODDS_FS).move_to(
                [num_x, self._ny(y, fs), 0], aligned_edge=anchor_num),
            run_time=run_time,
        )
        self._count([{"mob": num, "fmt": fmt, "x": num_x, "y": y, "start": prev,
                      "target": turn, "color": AVG_GREEN, "fs": fs, "anchor": anchor_num}], 0.9)

    def _build_probs_panel(self, base_band):
        yt, ym, yb = self._panel_ys(base_band)
        self._num_pos = {"p40": (self.ODDS_NX, yt), "p0": (self.ODDS_NX, ym),
                         "ev": (self.ODDS_NX, yb)}
        self.lbl_p40 = self._label("40 pts:", self.ODDS_CX, yt, fs=self.ODDS_FS, anchor=RIGHT)
        self.lbl_p0  = self._label("0 pts:",  self.ODDS_CX, ym, fs=self.ODDS_FS, anchor=RIGHT)
        self.lbl_ev  = self._label("Avg pts:", self.ODDS_CX, yb, fs=self.ODDS_FS, anchor=RIGHT)
        self.n_p40 = self._numlabel("0%", self.ODDS_NX, yt, fs=self.ODDS_FS)
        self.n_p0  = self._numlabel("0%", self.ODDS_NX, ym, fs=self.ODDS_FS)
        self.n_ev  = self._numlabel("0.00", self.ODDS_NX, yb, fs=self.ODDS_FS)

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
    def reroll_cycle(self):
        run_time = 0.6
        for name in ["34", "234", "246"]:
            self._show_keep(self.dice, self._KEEP_IDX[name], base_band=2, run_time=run_time)
            self._retarget(name, run_time=0.8)
            self.wait(0.35)
        self._show_keep(self.dice, self._KEEP_IDX["1234"], base_band=2, run_time=run_time)
        self._retarget("1234", run_time=0.8)
        self.play(self.n_ev.animate.set_color(AVG_GREEN), run_time=0.5)  # number only

    # ══════════════════════════════════════════════════════════════════════════
    # d : a couple more rolls with their best keep + numbers already in place
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def other_rolls(self):
        run_time = 0.6
        # the Avg number stays GREEN for these (best-keep) examples (number only)
        # script: "3 other dice configurations with their best dice combos forward"
        # — varied, and NOT all four-dice keeps (4 / 3 / 2 kept respectively).
        # Rolls + best keeps + rest-of-game numbers come from the solver cache.
        for entry in self.nums["other_rolls"]:
            values, keep_vec = entry["values"], entry["keep_vec"]
            ev = entry["ev"]
            self._regroup(self.dice, 2, run_time=0.5)
            morph_dice(self, self.dice, values, run_time=0.5)
            self._show_keep(self.dice, self._keep_indices(values, keep_vec),
                            base_band=2, run_time=run_time)
            p40, p0 = entry["p40"] * 100, entry["p0"] * 100
            (x40, y40), (x0, y0), (xev, yev) = (self._num_pos["p40"],
                                                self._num_pos["p0"], self._num_pos["ev"])
            self._count([
                {"mob": self.n_p40, "fmt": self._pct, "x": x40, "y": y40, "fs": self.ODDS_FS,
                 "start": self.n_p40_val, "target": p40},
                {"mob": self.n_p0,  "fmt": self._pct, "x": x0, "y": y0, "fs": self.ODDS_FS,
                 "start": self.n_p0_val, "target": p0},
                {"mob": self.n_ev,  "fmt": self._ev,  "x": xev, "y": yev, "fs": self.ODDS_FS,
                 "color": AVG_GREEN, "start": self.n_ev_val, "target": ev},
            ], run_time=0.8)
            self.n_p40_val, self.n_p0_val, self.n_ev_val = p40, p0, ev
            self.wait(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # e : step back to the FIRST reroll — 12446 at band 1, keep 24 (avg only)
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def first_reroll(self):
        run_time = 0.6
        self.play(FadeOut(VGroup(self.lbl_p40, self.lbl_p0, self.n_p40, self.n_p0)),
                  run_time=0.4)                                    # avg only now
        # move the dice DOWN to band 1 (3rd row) AND the Avg down to band 2 (2nd
        # row) AT THE SAME TIME (label right-anchored / number left-anchored so
        # they stay vertically aligned; number back to black).
        by = BAND_YS[2]
        self.play(*[self.dice[i].animate.move_to(slot_point(1, i)) for i in range(5)],
                  self.lbl_ev.animate.move_to([self.ODDS_CX, by, 0], aligned_edge=RIGHT),
                  self.n_ev.animate.set_color(BLACK).move_to([self.ODDS_NX, self._ny(by, self.ODDS_FS), 0], aligned_edge=LEFT),
                  run_time=0.5)
        # reset the running counter back to 0 now that it has moved to the new row
        # (the carried-over value was the previous roll's — start these fresh).
        self._count([{"mob": self.n_ev, "fmt": self._ev, "x": self.ODDS_NX, "y": by,
                      "start": self.n_ev_val, "target": 0.0, "fs": self.ODDS_FS}], 0.3)
        morph_dice(self, self.dice, [1, 2, 4, 4, 6], run_time=0.5)
        self.ev_y = by

        keep_idx = {"124": [0, 1, 2], "24": [1, 2], "246": [1, 2, 4]}
        prev = 0.0
        for name in ["124", "24", "246", "24"]:
            self._show_keep(self.dice, keep_idx[name], base_band=1, run_time=run_time)
            ev = self.nums["first_reroll"][name]["ev"]
            self._count([{"mob": self.n_ev, "fmt": self._ev, "x": self.ODDS_NX,
                          "y": by, "start": prev, "target": ev, "fs": self.ODDS_FS}], 0.8)
            prev = ev
            self.wait(0.3)
        self.n_ev_val = prev
        self.play(self.n_ev.animate.set_color(AVG_GREEN), run_time=0.5)  # number only

    # ══════════════════════════════════════════════════════════════════════════
    # f : a few first rolls (EV above), then dice to band 0 → one whole-turn EV
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def turn_ev(self):
        run_time = 0.6
        # FIRST PART like d: each first roll's best keep is SET FORWARD, with its
        # Avg pts (green number) — reusing the same panel label/number from e.
        by = BAND_YS[2]
        prev = self.n_ev_val
        # distinct rest-of-game EVs so the number changes (7.41 / 12.22 / 22.22);
        # rolls + best stage-A keeps come from the solver cache.
        for entry in self.nums["turn_ev_rolls"]:
            values, keep_vec, ev = entry["values"], entry["keep_vec"], entry["ev"]
            self._regroup(self.dice, 1, run_time=0.4)
            morph_dice(self, self.dice, values, run_time=0.5)
            self._show_keep(self.dice, self._keep_indices(values, keep_vec),
                            base_band=1, run_time=run_time)
            self._count([{"mob": self.n_ev, "fmt": self._ev, "x": self.ODDS_NX, "y": by,
                          "start": prev, "target": ev, "color": AVG_GREEN,
                          "fs": self.ODDS_FS}], 0.7)
            prev = ev
            self.wait(0.4)

        # END: dice to the beginning (band 0) + Avg pts to the middle of the 3rd
        # row, bigger, its number becoming the whole-turn EV (text stays "Avg pts:").
        self._land_turn_ev(self.dice, self.lbl_ev, self.n_ev, prev,
                           self.nums["turn_ev"], run_time=run_time)
        self.turn_lbl, self.turn_num = self.lbl_ev, self.n_ev

    # ══════════════════════════════════════════════════════════════════════════
    # g : box choice — 11134 with 4-Kind & Lg Straight open; compare "avg after"
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def box_choice(self):
        run_time = 0.6
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
        # HORIZONTAL arrows pointing LEFT — the arrowHEADS sit at the right edge of
        # each open box; the base (right) end reaches just PAST the right edge of the
        # card and carries the "Avg points after" words.
        head4 = self.card.value_cells[7].get_right()
        headls = self.card.value_cells[10].get_right()
        base_x = self.card.get_right()[0] + 0.12                  # just past the card edge
        ar4 = Arrow([base_x, c4[1], 0], head4, color=BLACK,
                    buff=0, stroke_width=3.5, max_tip_length_to_length_ratio=0.12)
        arls = Arrow([base_x, cls[1], 0], headls, color=BLACK,
                     buff=0, stroke_width=3.5, max_tip_length_to_length_ratio=0.12)
        box = self.nums["box_choice"]
        ev4 = box["fill_4kind"]["total"]          # zero 4-Kind, keep Lg Straight open
        evls = box["fill_lgstraight"]["total"]    # zero Lg Straight, keep 4-Kind open
        # Keep the label and its number as SEPARATE mobjects: the full
        # "Avg points remaining: 10.6" string is wide enough at fs24 to hit
        # crisp_text's wrap width and break onto two lines (the shorter 5.6 one
        # doesn't) — the label alone is safe.
        lab4 = self._label("Avg points remaining:", base_x + 0.2, c4[1], anchor=LEFT, fs=24)
        num4 = self._numlabel(f"{ev4:.1f}", lab4.get_right()[0] + 0.15, c4[1], fs=24)
        labls = self._label("Avg points remaining:", base_x + 0.2, cls[1], anchor=LEFT, fs=24)
        numls = self._numlabel(f"{evls:.1f}", labls.get_right()[0] + 0.15, cls[1], fs=24)

        self.play(FadeIn(z4), FadeIn(zls), run_time=0.5)          # the 0s appear in the boxes
        self.wait(0.4)
        # the arrows grow in AT THE SAME TIME as the "Avg points remaining" text
        self.play(GrowArrow(ar4), GrowArrow(arls),
                  FadeIn(lab4), FadeIn(num4), FadeIn(labls), FadeIn(numls), run_time=0.6)
        self.wait(0.6)

        # zero out the LOWER-EV box (keep the higher-value one open) → the 4-Kind
        self.play(FadeOut(VGroup(ar4, arls, z4, zls, lab4, num4, labls, numls)), run_time=0.4)
        zero_row = 7 if ev4 >= evls else 10
        self.card.animate_zero_score(self, zero_row, self.dice)
        self.wait(0.4)
        self.play(FadeOut(VGroup(*self.dice)), run_time=0.4)
        self.dice = None

    # ══════════════════════════════════════════════════════════════════════════
    # h : the backward-induction montage — like d/e, repeated GOING DOWN the rows
    #     (rows count from the top). Full-size dice; the optimal keep is SET FORWARD
    #     (rises a band); the EV sits above-right (in the row above the base dice).
    #     Row 2 dice → EV row 1; then row 3 dice → EV row 2; then the whole-turn EV
    #     at the bottom (row 4). Going backwards, so 4-of-a-Kind is unfilled.
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def keep_montage(self):
        run_time = 0.6
        self.card.transition(self, {7: None}, run_time=0.6)       # 4-Kind unfilled again
        dice = [get_die(1) for _ in range(5)]                     # same size as always
        montage = self.nums["montage"]                            # solver, 2-open-box state
        start = self.nums["turn_ev"]                              # continue from beat f's value

        # "Avg points remaining:" is too wide for the right column here, so stack it
        # on 2 lines with the green number on the "remaining:" line. The counter
        # PICKS UP from beat f's turn value (not 0).
        ev_lbl, line2_dy = self._remaining_label(self.ODDS_CX, BAND_YS[3], self.ODDS_FS)
        ev_num = self._numlabel(self._ev(start), self.ODDS_NX, BAND_YS[3] + line2_dy,
                                color=AVG_GREEN, fs=self.ODDS_FS)
        for s, d in enumerate(dice):                              # reveal in row 2 (band 2)
            d.set_value(montage[0]["values"][s])
            d.move_to(slot_point(2, s))
        self.play(*[FadeIn(d) for d in dice], FadeIn(ev_lbl), FadeIn(ev_num), run_time=0.5)

        prev = [start]

        def _roll(entry, *, move_avg):
            values, keep_vec, ev = entry["values"], entry["keep_vec"], entry["ev"]
            # 2nd-reroll (stage B) rolls sit in row 2 (band 2), EV in row 1 above;
            # 1st-reroll (stage A) rolls sit in row 3 (band 1), EV in row 2 above.
            base_band = 2 if entry["stage"] == "B" else 1
            ev_band = base_band + 1
            num_y = BAND_YS[ev_band] + line2_dy                   # number sits on the "remaining:" line
            # flatten the dice at `base_band`; on a row change, the avg moves down
            # to `ev_band` AT THE SAME TIME (not first).
            anims = [dice[i].animate.move_to(slot_point(base_band, i)) for i in range(5)]
            if move_avg:
                anims += [ev_lbl.animate.move_to([self.ODDS_CX, BAND_YS[ev_band], 0], aligned_edge=RIGHT),
                          ev_num.animate.move_to([self.ODDS_NX, self._ny(num_y, self.ODDS_FS), 0], aligned_edge=LEFT)]
            self.play(*anims, run_time=0.4)
            morph_dice(self, dice, values, run_time=0.4)
            self._show_keep(dice, self._keep_indices(values, keep_vec),
                            base_band=base_band, run_time=run_time)          # SET FORWARD
            self._count([{"mob": ev_num, "fmt": self._ev, "x": self.ODDS_NX,
                          "y": num_y, "start": prev[0], "target": ev,
                          "color": AVG_GREEN, "fs": self.ODDS_FS}], 0.5)
            prev[0] = ev
            self.wait(0.25)

        # walk the montage backward: the two 2nd-reroll rolls (row 2), then the two
        # 1st-reroll rolls (row 3) — dropping a row (and moving the avg down with
        # the dice) exactly when the reroll stage changes from B to A.
        prev_band = 2
        for entry in montage:
            base_band = 2 if entry["stage"] == "B" else 1
            _roll(entry, move_avg=(base_band != prev_band))
            prev_band = base_band

        # dice to the bottom row + the value to the 3rd row, single line — landing
        # DIRECTLY in beat i's layout (its size/position, one decimal) so nothing
        # jumps size or shifts left at the h→i hand-off.
        self._land_turn_ev(dice, ev_lbl, ev_num, prev[0],
                           self.nums["montage_turn_ev"], run_time=run_time,
                           label="Avg points remaining:", fs=32,
                           lbl_x=slot_x(2) - 0.6, num_x=slot_x(2) + 2.7,
                           anchor_lbl=ORIGIN, anchor_num=ORIGIN, fmt=self._onedp)
        # leave the dice + value ON SCREEN — the sweep (beat i) continues from them.
        self.h_dice, self.h_ev_lbl, self.h_ev_num = dice, ev_lbl, ev_num

    # ══════════════════════════════════════════════════════════════════════════
    # i : empty the card box-by-box; REAL "avg points remaining" (solver V) → 254.6
    # ══════════════════════════════════════════════════════════════════════════
    @subscene
    def backward_sweep(self):
        run_time = 0.8
        # Continue STRAIGHT from the montage: beat h already landed the value in THIS
        # layout ("Avg points remaining: 21.2", V ≈ 21.2) with the dice below, on the
        # SAME running-example card (4-Kind + Large Straight open). Just keep emptying.
        by = BAND_YS[1]                          # the EV lives in the 3rd row (top-down)
        xn = slot_x(2) + 2.7
        seq = self.nums["sweep"]                 # seq[0] ≈ 21.2 = the montage turn value
        num = self.h_ev_num                      # count on the carried-over mob

        prev = seq[0]["remaining"]
        for step in seq[1:]:
            self.card.transition(self, {_sc_box(step["emptied"]): None}, run_time=0.45)
            self._count([{"mob": num, "fmt": self._onedp, "x": xn, "y": by,
                          "start": prev, "target": step["remaining"],
                          "color": AVG_GREEN, "anchor": ORIGIN, "fs": 32}], 0.4)
            prev = step["remaining"]
            self.wait(0.15)
