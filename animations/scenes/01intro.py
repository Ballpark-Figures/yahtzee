from pathlib import Path
import sys
from itertools import combinations_with_replacement
from math import factorial

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.dice import get_die, slot_point
from assets.scorecard import get_scorecard


# ── the 252 distinct outcomes, in the model's canonical (np.unique) order ──────
def _all_outcomes():
    """(values_tuple, n_arrangements) for each of the 252 distinct 5-dice rolls,
    sorted by face-count vector (same order the solver uses)."""
    rows = []
    for combo in combinations_with_replacement(range(1, 7), 5):
        vec = [combo.count(f) for f in range(1, 7)]
        ways = factorial(5)
        for c in vec:
            ways //= factorial(c)
        rows.append((tuple(vec), combo, ways))
    rows.sort(key=lambda r: r[0])           # np.unique-style lexicographic sort
    return [(combo, ways) for _, combo, ways in rows]


class Intro(YahtzeeScene):
    """Scene 01 — the staggering number of Yahtzee positions.

    Follows the script's animation column beat-for-beat:
      one_die      — 6 dice outcomes (faces 1-6)
      all_outcomes — all 252 distinct 5-dice outcomes; then shrink the less likely
      three_rolls  — 3 rolls bottom->top, then 252 fanning out from each (756)
      box_combos   — blink the 13 card boxes, multiply 2's -> 8192
      one_card     — cycle filled scorecards -> 385,647,100,272
      grand_total  — count 385B down to 341,960,288,112, x756 -> 258,521,977,812,672
    """

    def setup_scene(self):
        pass

    # ── 6 things can happen ───────────────────────────────────────────────────
    @subscene
    def one_die(self):
        die = get_die(1, size=1.3).move_to(ORIGIN)
        self.play(FadeIn(die))
        self.wait(1)

        faces = VGroup(*[get_die(v, size=0.9) for v in range(1, 7)])
        faces.arrange(RIGHT, buff=0.45).move_to(ORIGIN)
        self.play(Transform(die, faces[0]),
                  *[FadeIn(f) for f in faces[1:]])
        self.wait(1)
        self.play(FadeOut(die), *[FadeOut(f) for f in faces[1:]])

    # ── 252 distinct outcomes, then shrink the less likely ────────────────────
    @subscene
    def all_outcomes(self):
        outcomes = _all_outcomes()                       # 252 of them

        def mini(vals, s=0.11):
            g = VGroup(*[get_die(v, size=s) for v in vals])
            g.arrange(RIGHT, buff=0.015)
            return g

        groups = VGroup(*[mini(vals) for vals, _ in outcomes])
        groups.arrange_in_grid(rows=14, cols=18, buff=(0.16, 0.32))
        groups.scale_to_fit_width(14.6)
        if groups.height > 7.6:
            groups.scale_to_fit_height(7.6)
        groups.move_to(ORIGIN)

        self.play(LaggedStart(*[FadeIn(g) for g in groups],
                              lag_ratio=0.004, run_time=2))
        self.wait(1)

        # shrink each outcome by how likely it is (fewer arrangements -> smaller)
        ways = [w for _, w in outcomes]
        wmax = max(ways)
        self.play(*[g.animate.scale(0.25 + 0.75 * (w / wmax))
                    for g, w in zip(groups, ways)], run_time=1.5)
        self.wait(1)
        self.play(FadeOut(groups))
        self.groups_outcomes = groups   # reused conceptually in three_rolls

    # ── 3 rolls bottom->top, then 252 fanning from each ───────────────────────
    @subscene
    def three_rolls(self):
        # three roll rows stacking from the bottom upward
        ys = [-2.6, -0.2, 2.2]
        roll_vals = [[2, 4, 6, 1, 3], [4, 4, 6, 5, 3], [4, 4, 6, 6, 2]]
        rows = VGroup()
        for vals, y in zip(roll_vals, ys):
            row = VGroup(*[get_die(v, size=0.55) for v in vals])
            row.arrange(RIGHT, buff=0.18).move_to([-5.2, y, 0])
            rows.add(row)
        for row in rows:
            self.play(FadeIn(row, shift=UP * 0.3))
            self.wait(1)

        # 252 fanning out from the top roll
        def fan(vals, s=0.07):
            g = VGroup(*[get_die(v, size=s) for v in vals])
            g.arrange(RIGHT, buff=0.01)
            return g

        outcomes = _all_outcomes()
        fan_grid = VGroup(*[fan(vals) for vals, _ in outcomes])
        fan_grid.arrange_in_grid(rows=14, cols=18, buff=(0.10, 0.20))
        fan_grid.scale_to_fit_width(9.5).move_to([2.6, 0, 0])
        arrow = Arrow(rows[2].get_right(), fan_grid.get_left(),
                      color=BLACK, buff=0.25)
        self.play(GrowArrow(arrow),
                  LaggedStart(*[FadeIn(g) for g in fan_grid],
                              lag_ratio=0.003, run_time=1.5))
        self.wait(1)
        self.play(FadeOut(rows), FadeOut(arrow), FadeOut(fan_grid))

    # ── blink the 13 boxes, multiply 2's -> 8192 ──────────────────────────────
    @subscene
    def box_combos(self):
        sc = get_scorecard(center=[-3.6, 0, 0], scores=[None] * 14).scale(0.92)
        self.play(FadeIn(sc))
        self.wait(1)

        boxes = VGroup(*[sc.value_cells[r] for r in range(13)])
        on = VGroup(*[b.copy().set_fill(SCORE_GREEN, opacity=0.65).set_stroke(width=0)
                      for b in boxes])
        self.add(on)
        for _ in range(2):
            self.play(on.animate.set_opacity(0.0), run_time=0.5)
            self.play(on.animate.set_opacity(0.65), run_time=0.5)
        self.remove(on)

        # 2 x 2 x ... (13 twos) = 8192, built up on the right
        twos = VGroup(*[crisp_text("2", font_size=44, color=BLACK, font=FONT, weight="BOLD")
                        for _ in range(13)])
        twos.arrange(RIGHT, buff=0.3).move_to([3.4, 1.4, 0])
        for i, t in enumerate(twos):
            self.play(FadeIn(t, shift=UP * 0.2), run_time=0.15)
        self.wait(1)
        result = crisp_text("8,192", font_size=90, color=BOARD_FILL, font=FONT, weight="BOLD")
        result.move_to([3.4, -0.6, 0])
        self.play(TransformFromCopy(twos, result))
        self.wait(1)
        self.play(FadeOut(sc), FadeOut(twos), FadeOut(result))

    # ── cycle filled scorecards -> 385,647,100,272 ────────────────────────────
    @subscene
    def one_card(self):
        sc = get_scorecard(center=[-3.6, 0, 0],
                           scores=[3, 8, 9, 4, 15, 12, 22, 0, 25, 30, 0, 50, 17, 0]).scale(0.92)
        self.play(FadeIn(sc))
        self.wait(1)

        # rapidly cycle a few different fully-filled cards in place
        fills = [
            [1, 6, 12, 16, 5, 24, 18, 0, 0, 30, 40, 0, 21, 0],
            [3, 4, 6, 12, 20, 18, 26, 28, 25, 0, 40, 50, 19, 0],
            [2, 2, 9, 8, 10, 6, 0, 0, 25, 30, 0, 0, 24, 0],
        ]
        for f in fills:
            new = get_scorecard(center=[-3.6, 0, 0], scores=f).scale(0.92)
            self.play(Transform(sc, new), run_time=0.5)
            self.wait(1)

        num = crisp_text("385,647,100,272", font_size=58, color=BOARD_FILL, font=FONT, weight="BOLD")
        num.move_to([3.4, 0, 0])
        self.play(Write(num))
        self.wait(1)
        self.play(FadeOut(sc))
        self.num_per_card = num   # carry into grand_total

    # ── 385B down to 341,960,288,112, x756 -> 258,521,977,812,672 ─────────────
    @subscene
    def grand_total(self):
        num = self.num_per_card
        self.play(num.animate.move_to([0, 1.8, 0]))

        tracker = ValueTracker(385_647_100_272)
        counter = always_redraw(lambda: crisp_text(
            f"{int(tracker.get_value()):,}", font_size=58, color=BOARD_FILL,
            font=FONT, weight="BOLD").move_to([0, 1.8, 0]))
        self.remove(num)
        self.add(counter)
        self.play(tracker.animate.set_value(341_960_288_112), run_time=2)
        self.wait(1)

        mult = crisp_text("× 756", font_size=64, color=BLACK, font=FONT, weight="BOLD")
        mult.move_to([0, 0.4, 0])
        self.play(FadeIn(mult, shift=UP * 0.2))
        self.wait(1)

        total = crisp_text("258,521,977,812,672", font_size=72, color=BOARD_FILL,
                           font=FONT, weight="BOLD").move_to([0, -1.5, 0])
        self.play(TransformFromCopy(counter, total))
        self.wait(1)
