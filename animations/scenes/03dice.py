from pathlib import Path
import sys
from itertools import combinations_with_replacement, permutations, product

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.dice import get_die, DIE_COLORS, PIP_COLORS


# ── outcome enumeration ───────────────────────────────────────────────────────
def _multisets(k):
    """Canonical ascending k-multisets of 1..6 (same order scene 1 uses)."""
    return list(combinations_with_replacement(range(1, 7), k))


# the 120 orderings of the 5 colored dice (used for the straight permutations)
_COLOR_PERMS = list(permutations(DIE_COLORS))

# 6^k build-up as nested clusters of colored squares. We show 6 REAL dice first,
# morph them to squares while there are only 6 (the smoothest moment), then grow
# 6 → 36 → 216 → 1296 → 7776 — each k-group spawns 6 (k+1)-groups by appending
# 1..6 (scene-1's grow style). Lex-ordered by (d1,…,dk): outermost split = first
# die, appended (last) die = innermost. Box stays full-frame and just subdivides.
_BUILD_W, _BUILD_H = 15.6, 8.6
_CELL_GAP = 0.04          # gap between sibling cells, as a fraction of the box
# Per-die 6-split (rows, cols), outermost (d1) first. Singles are square → 2×3;
# deeper levels use 3×2 so cells stay WIDE to match the widening k-die rows. This
# keeps dice as large as possible instead of letting them collapse ~6×/level.
_SPLIT_SHAPES = [(2, 3), (3, 2), (3, 2), (3, 2), (3, 2)]

# frequency classes: (example combo, # of ways), sorted most→least.
_FREQ = [
    ((1, 2, 3, 4, 5), 120),   # all different (incl. both large straights)
    ((1, 1, 2, 3, 4), 60),    # one pair
    ((1, 1, 2, 2, 3), 30),    # two pair
    ((1, 1, 1, 2, 3), 20),    # three of a kind
    ((1, 1, 1, 2, 2), 10),    # full house
    ((1, 1, 1, 1, 2), 5),     # four of a kind
    ((1, 1, 1, 1, 1), 1),     # yahtzee
]


# ── layout helpers ────────────────────────────────────────────────────────────
_MARGIN = 0.25


def _fit(group, w=16 - 2 * _MARGIN, h=9 - 2 * _MARGIN, center=ORIGIN):
    """Scale `group` to sit inside a box (whichever dimension binds) + center."""
    group.scale_to_fit_width(w)
    if group.height > h:
        group.scale_to_fit_height(h)
    group.move_to(center)
    return group


# Scene-1's equal-margin fit, replicated verbatim so the 252 grid in `b` looks
# IDENTICAL to scene 1's (its helpers live in 01intro.py, which can't be imported
# — the module name starts with a digit). Margin 0.15; rows are stretched to fill
# the height so the vertical margin matches the horizontal one.
_SC1_FIT_W, _SC1_FIT_H = 15.7, 8.7


def _fit_equal_margins(group):
    group.scale_to_fit_width(_SC1_FIT_W)
    if group.height > _SC1_FIT_H:
        group.scale_to_fit_height(_SC1_FIT_H)
    group.move_to(ORIGIN)
    return group


def _balance_rows(group, rows):
    if rows < 2 or group.height >= _SC1_FIT_H - 1e-3:
        return group
    factor = _SC1_FIT_H / group.height
    cy = group.get_center()[1]
    for sub in group:
        x, y, z = sub.get_center()
        sub.move_to([x, cy + (y - cy) * factor, z])
    return group


def _label(text, font_size=44):
    return crisp_text(text, font_size=font_size, color=BLACK, font=FONT,
                      weight="BOLD")


def _cluster_centers(splits, cx, cy, w, h):
    """Cell centers for nested per-die splits, lex order (splits[0] = first die).
    Each split is (rows, cols) with rows*cols == 6."""
    if not splits:
        return [(cx, cy)]
    (r, c), rest = splits[0], splits[1:]
    gx, gy = w * _CELL_GAP, h * _CELL_GAP
    cw, ch = (w - (c - 1) * gx) / c, (h - (r - 1) * gy) / r
    out = []
    for val in range(6):
        rr, cc = divmod(val, c)
        scx = cx + (cc - (c - 1) / 2.0) * (cw + gx)
        scy = cy + ((r - 1) / 2.0 - rr) * (ch + gy)
        out.extend(_cluster_centers(rest, scx, scy, cw, ch))
    return out


def _leaf_cell(level):
    """Size (w, h) of one leaf cell after the level's nested splits."""
    w, h = _BUILD_W, _BUILD_H
    for (r, c) in _SPLIT_SHAPES[:level]:
        w = (w - (c - 1) * w * _CELL_GAP) / c
        h = (h - (r - 1) * h * _CELL_GAP) / r
    return w, h


def _die_size(k):
    """Largest die so a k-die row fits the leaf cell (tight packing)."""
    cw, ch = _leaf_cell(k)
    bf = 0.06   # inter-die buff as a fraction of die size
    return max(min(cw * 0.98 / (k + bf * (k - 1)), ch * 0.94), 0.01)


def _build_level(level):
    """6^level dice-groups (colored pips), lex order, placed in the 2×3 fractal."""
    size = _die_size(level)
    centers = _cluster_centers(_SPLIT_SHAPES[:level], 0.0, 0.0, _BUILD_W, _BUILD_H)
    groups = []
    for i, tup in enumerate(product(range(1, 7), repeat=level)):
        g = _pip_row(list(tup), size=size, buff=size * 0.06)
        cx, cy = centers[i]
        g.move_to([cx, cy, 0.0])
        groups.append(g)
    return groups


def _square(value, size):
    """A rounded square in `value`'s color (the colored-pip palette)."""
    return RoundedRectangle(width=size, height=size, corner_radius=size * 0.22,
                            fill_color=PIP_COLORS[value], fill_opacity=1.0,
                            stroke_width=0)


def _build_square_level(level):
    """Like _build_level, but each die is a rounded colored square — used once the
    groups get too small to read as pip-dice."""
    size = _die_size(level)
    centers = _cluster_centers(_SPLIT_SHAPES[:level], 0.0, 0.0, _BUILD_W, _BUILD_H)
    groups = []
    for i, tup in enumerate(product(range(1, 7), repeat=level)):
        g = VGroup(*[_square(v, size) for v in tup]).arrange(RIGHT, buff=size * 0.06)
        cx, cy = centers[i]
        g.move_to([cx, cy, 0.0])
        groups.append(g)
    return groups


def _colored_row(values, colors, size, buff=0.05):
    """A row of dice with COLORED BODIES (black pips/border) — colored-dice mode."""
    g = VGroup(*[get_die(v, size=size, body_color=c)
                 for v, c in zip(values, colors)])
    g.arrange(RIGHT, buff=buff)
    return g


def _pip_row(values, size, buff=0.05):
    """A row of dice with value-COLORED PIPS (beige body) — colored-pip mode."""
    g = VGroup(*[get_die(v, size=size, pip_coloring=True) for v in values])
    g.arrange(RIGHT, buff=buff)
    return g


class Dice(YahtzeeScene):
    """Scene 03 — understanding dice: 6^5 outcomes, but only 252 distinct ones,
    and those 252 occur in wildly different numbers of ways.

      powers              — 6^5 as dot grids: 6 → 36 → 216 → 1296 → 7776
      to_252              — the 7776 dots collapse into the 252 distinct outcomes
      yahtzee_ways        — a yahtzee in 5 colored dice → only 1 way
      straight_120        — a 1-5 straight, all 120 color arrangements → 120 ways
      straights_vs_yahtzees — 240 straights vs 6 yahtzees → ~40x more likely
      frequency_table     — every frequency class with # of ways, sorted
    """

    # vertical center the big dot/outcome grids sit at (top strip left for the
    # running count label).
    GRID_CY = -0.35
    LABEL_Y = 3.7

    def setup_scene(self):
        self._setup_powers()
        self._setup_252()
        self._setup_yahtzee()
        self._setup_straight_120()
        self._setup_straights_vs()
        self._setup_frequency()

    # ── construction ──────────────────────────────────────────────────────────
    def _setup_powers(self):
        # 6 real dice, then squares all the way: morph at 6, grow to 7776.
        self.lv1 = _build_level(1)              # the 6 singles, as real dice
        self.lv1_sq = _build_square_level(1)
        self.lv2_sq = _build_square_level(2)
        self.lv3_sq = _build_square_level(3)
        self.lv4_sq = _build_square_level(4)
        self.lv5_sq = _build_square_level(5)
        self.power_final = None   # the last level; consumed by to_252

    def _setup_252(self):
        # EXACTLY scene 1's 252 grid: same dice size (0.24) + intra-group buff
        # (0.025), same (21, 12) shape, inter-group buff (0.1) = 4×, column-major
        # "dr" fill, and scene 1's equal-margin fit + row-balance (fills the frame,
        # centered — no top gap).
        groups = VGroup(*[_pip_row(c, size=0.24, buff=0.025)
                          for c in _multisets(5)])
        groups.arrange_in_grid(rows=21, cols=12, buff=(0.1, 0.1),
                               flow_order="dr")
        _fit_equal_margins(groups)
        _balance_rows(groups, 21)
        self.grid252 = groups

    def _setup_yahtzee(self):
        # all five dice show the same value, each a different color → still 1 way
        self.yz_dice = _colored_row([3, 3, 3, 3, 3], DIE_COLORS,
                                    size=1.0, buff=0.25)
        self.yz_dice.move_to(ORIGIN)

    def _setup_straight_120(self):
        # 120 1-5 straights (all color orderings), 15×8 grid filled down the rows.
        # Tight buffs + full height so the dice render as large as 120 of them fit.
        groups = VGroup(*[_colored_row([1, 2, 3, 4, 5], perm, size=0.2, buff=0.04)
                          for perm in _COLOR_PERMS])
        groups.arrange_in_grid(rows=15, cols=8, buff=(0.25, 0.12), flow_order="dr")
        _fit(groups, h=8.5, center=ORIGIN)
        self.s120 = groups

    def _setup_straights_vs(self):
        # 240 large straights split into halves (script: 120 1-5 on top, 120 2-6
        # on bottom). Each half is a 10×12 grid filled down the rows; stacked, the
        # pair reads as a 20×12 grid. Block sits on the left, opposite the yahtzees.
        def _half(values):
            g = VGroup(*[_colored_row(values, p, size=0.14, buff=0.03)
                         for p in _COLOR_PERMS])
            g.arrange_in_grid(rows=15, cols=8, buff=(0.18, 0.14), flow_order="dr")
            return g

        self.s240_top = _half([1, 2, 3, 4, 5])
        self.s240_bot = _half([2, 3, 4, 5, 6])
        block = VGroup(self.s240_top, self.s240_bot).arrange(DOWN, buff=0.5)
        _fit(block, w=9.5, h=7.6, center=[-3.0, 0.0, 0])
        self.s240 = block

        # 6 yahtzees (one per value), colored dice, stacked on the right.
        yz = VGroup(*[_colored_row([v] * 5, DIE_COLORS, size=0.18, buff=0.03)
                      for v in range(1, 7)])
        yz.arrange(DOWN, buff=0.25)
        yz.move_to([5.0, 0.0, 0])
        self.six_yz = yz

    def _setup_frequency(self):
        self.freq_title = _label("Dice Combo Frequencies", font_size=44)
        self.freq_title.move_to([0, 3.7, 0])
        rows = VGroup()
        ys = [2.7, 1.8, 0.9, 0.0, -0.9, -1.8, -2.7]
        for (combo, ways), y in zip(_FREQ, ys):
            dice = _pip_row(combo, size=0.6, buff=0.06).move_to([-2.6, y, 0])
            word = "way" if ways == 1 else "ways"
            count = _label(f"{ways} {word}", font_size=40)
            count.move_to([1.6, y, 0], aligned_edge=LEFT)
            rows.add(VGroup(dice, count))
        self.freq_rows = rows

    # ── a. 6^k build-up: each k-group spawns 6 (k+1)-groups (append 1..6) ───────
    def _grow(self, parents, children, k, run_time, lag_ratio=0.002):
        """Scene-1 style grow: parent p's 6 children are children[p*6 : p*6+6]
        (same first k dice, appended die = 1..6). Each child's seed is copies of
        the parent's k dice plus the new die, which starts hidden on the parent's
        last die and fades in as the seed transforms into the child."""
        seeds, transforms = [], []
        for p, parent in enumerate(parents):
            for j in range(6):
                child = children[p * 6 + j]
                new_die = child[k].copy().set_opacity(0.0).move_to(parent[k - 1])
                seed = VGroup(*[parent[d].copy() for d in range(k)], new_die)
                seeds.append(seed)
                transforms.append(Transform(seed, child))
        self.add(*seeds)
        self.remove(*parents)
        self.play(LaggedStart(*transforms, lag_ratio=lag_ratio), run_time=run_time)
        self.remove(*seeds)
        self.add(*children)
        return children

    @subscene
    def powers(self):
        self.play(LaggedStart(*[FadeIn(g) for g in self.lv1], lag_ratio=0.08),
                  run_time=1.0)
        self.wait(0.4)
        # only 6 dice on screen — the smoothest moment to switch to colored squares
        self.play(*[ReplacementTransform(d, s)
                    for d, s in zip(self.lv1, self.lv1_sq)], run_time=0.8)
        self.wait(0.3)
        self._grow(self.lv1_sq, self.lv2_sq, 1, run_time=1.4)
        self.wait(0.3)
        self._grow(self.lv2_sq, self.lv3_sq, 2, run_time=1.8)
        self.wait(0.3)
        self._grow(self.lv3_sq, self.lv4_sq, 3, run_time=2.0)
        self.wait(0.3)
        self._grow(self.lv4_sq, self.lv5_sq, 4, run_time=2.4)
        self.power_final = VGroup(*self.lv5_sq)
        self.wait(0.6)

    # ── b. 7776 raw outcomes → 252 distinct ones (scene-1 callback) ────────────
    @subscene
    def to_252(self):
        # crossfade, NOT a morph: ReplacementTransform-ing the 7776 dots into the
        # 1260-die grid (~10k paths) is brutally slow (the b slowdown). Kept as a
        # fade. The label is just text, so it morphs cheaply.
        self.play(
            FadeOut(self.power_final, scale=0.85),
            FadeIn(self.grid252),
            run_time=1.2,
        )
        self.wait(1.0)

    # ── c. a yahtzee in colored dice → only 1 way ──────────────────────────────
    @subscene
    def yahtzee_ways(self):
        self.play(FadeOut(self.grid252), run_time=0.6)
        self.play(FadeIn(self.yz_dice), run_time=0.6)
        self.wait(0.8)

    # ── d. a 1-5 straight in all 120 color arrangements → 120 ways ─────────────
    @subscene
    def straight_120(self):
        self.play(FadeOut(self.yz_dice), run_time=0.6)
        self.play(FadeIn(self.s120), run_time=0.8)
        self.wait(0.8)

    # ── e. 240 straights vs 6 yahtzees → ~40x ──────────────────────────────────
    @subscene
    def straights_vs_yahtzees(self):
        self.play(FadeOut(self.s120), run_time=0.6)
        self.play(FadeIn(self.s240), FadeIn(self.six_yz), run_time=0.9)
        self.wait(1.0)

    # ── f. frequency table: example combo (colored pips) + # of ways ───────────
    @subscene
    def frequency_table(self):
        self.play(FadeOut(self.s240), FadeOut(self.six_yz), run_time=0.6)
        self.play(FadeIn(self.freq_title, shift=DOWN * 0.2), run_time=0.5)
        self.play(LaggedStart(*[FadeIn(r, shift=RIGHT * 0.2)
                                for r in self.freq_rows],
                              lag_ratio=0.15, run_time=1.8))
        self.wait(1.0)
