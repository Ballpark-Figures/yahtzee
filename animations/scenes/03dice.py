from pathlib import Path
import sys
from itertools import combinations_with_replacement, permutations, product

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.dice import get_die, DIE_COLORS, PIP_COLORS, morph_dice


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

    # one knob for the whole build-up: every n→n+1 grow transition in `a` runs for
    # this many seconds (uniform). Tune this single value to retime all of them.
    GROW_RT = 1.8
    GRID_CY = -0.35
    LABEL_Y = 3.7

    # LAZY BUILDING — no setup_scene front-loads everything. Each subscene builds
    # the mobjects it OWNS (its first appearance), animates, and drops them once
    # consumed; carry-over objects ride forward in the snapshot. This keeps every
    # snapshot light AND makes a setup edit invalidate only its owner subscene
    # onward instead of the whole scene. Owners: singles→lv1/lv1_sq,
    # grow_NN→lvN_sq, to_252→grid252, yahtzee_ways→yz_dice, straight_120→s120,
    # straights_vs_yahtzees→s240/six_yz, frequency_table→freq_*. The _setup_<name>
    # helpers below are called by their owner subscene, not by a setup_scene.
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
        # 5 PLAIN (uncolored) dice, all showing 3 — a yahtzee. c colors them, then
        # swaps two dice's pips to show that swapping identical dice changes nothing.
        self.yz_dice = VGroup(*[get_die(3, size=1.0) for _ in range(5)])
        self.yz_dice.arrange(RIGHT, buff=0.25).move_to([0, 0.5, 0])

    def _setup_straight_120(self):
        # 120 1-5 straights (all color orderings), 15×8 down the rows, FULL SCREEN
        # (no label now). s120[0] (top-left) is the identity coloring 1=red…5=blue,
        # which the 5 dice from d shrink into.
        groups = VGroup(*[_colored_row([1, 2, 3, 4, 5], perm, size=0.2, buff=0.04)
                          for perm in _COLOR_PERMS])
        groups.arrange_in_grid(rows=15, cols=8, buff=(0.25, 0.15), flow_order="dr")
        # equal-margin fit + row-balance (like the 252 grid) → fills full height
        _fit_equal_margins(groups)
        _balance_rows(groups, 15)
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
        _fit(block, w=9.0, h=6.6, center=[-3.0, -0.5, 0])   # shrunk: room for label
        self.s240 = block

        # 6 yahtzees (one per value), colored dice, stacked on the right — bigger.
        yz = VGroup(*[_colored_row([v] * 5, DIE_COLORS, size=0.4, buff=0.05)
                      for v in range(1, 7)])
        yz.arrange(DOWN, buff=0.3)
        yz.move_to([5.0, 0.0, 0])
        self.six_yz = yz

        # "240" up at the top (room above the shrunk block); "6" above the yahtzees
        self.s240_label = _label("240").move_to([-3.0, 3.7, 0])
        self.six_label = _label("6").next_to(yz, UP, buff=0.6)

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

    # Each n→n+1 transition is its own subscene (so they can be rendered/tuned
    # independently). All grows share the single GROW_RT knob.
    @subscene
    def singles(self):
        self.lv1 = _build_level(1)              # owns lv1, lv1_sq
        self.lv1_sq = _build_square_level(1)
        self.play(LaggedStart(*[FadeIn(g) for g in self.lv1], lag_ratio=0.08),
                  run_time=1.0)
        self.wait(0.4)
        # only 6 dice on screen — smoothest moment to switch to colored squares
        self.play(*[ReplacementTransform(d, s)
                    for d, s in zip(self.lv1, self.lv1_sq)], run_time=0.8)
        self.lv1 = None                         # consumed
        self.wait(0.3)

    @subscene
    def grow_36(self):
        self.lv2_sq = _build_square_level(2)
        self._grow(self.lv1_sq, self.lv2_sq, 1, run_time=self.GROW_RT)
        self.lv1_sq = None                      # consumed
        self.wait(0.3)

    @subscene
    def grow_216(self):
        self.lv3_sq = _build_square_level(3)
        self._grow(self.lv2_sq, self.lv3_sq, 2, run_time=self.GROW_RT)
        self.lv2_sq = None
        self.wait(0.3)

    @subscene
    def grow_1296(self):
        self.lv4_sq = _build_square_level(4)
        self._grow(self.lv3_sq, self.lv4_sq, 3, run_time=self.GROW_RT)
        self.lv3_sq = None
        self.wait(0.3)

    @subscene
    def grow_7776(self):
        self.lv5_sq = _build_square_level(5)   # 38,880 squares
        self._grow(self.lv4_sq, self.lv5_sq, 4, run_time=self.GROW_RT)
        self.wait(0.6)
        # keep only the 252 ascending (distinct) quints; drop the other 7524
        # instantly so the snapshot stays light and to_252 animates just the 252.
        asc = [pi for pi, t in enumerate(product(range(1, 7), repeat=5))
               if all(t[i] <= t[i + 1] for i in range(4))]
        asc_set = set(asc)
        self.remove(*[g for i, g in enumerate(self.lv5_sq) if i not in asc_set])
        self.power_asc = [self.lv5_sq[i] for i in asc]   # 252, multiset order
        self.lv4_sq = self.lv5_sq = None        # consumed / culled

    # ── b. 7776 raw outcomes → 252 distinct ones (scene-1 callback) ────────────
    @subscene
    def to_252(self):
        # owns grid252; power_asc (the 252 ascending squares) carried in from
        # grow_7776. The k-th ascending square-quint maps to grid252[k] (product()
        # and combinations_with_replacement() share lex order) — morph each back
        # into its dice form and move it to the ordered grid slot.
        self._setup_252()
        self.play(*[ReplacementTransform(self.power_asc[mi], self.grid252[mi])
                    for mi in range(len(self.power_asc))], run_time=1.8)
        self.power_asc = None                   # consumed
        self.wait(1.0)

    # ── c. yahtzee: color the dice, swap two pips → still one arrangement ───────
    @subscene
    def yahtzee_ways(self):
        self._setup_yahtzee()                   # owns yz_dice (grid252 carried in)
        self.play(FadeOut(self.grid252), run_time=0.6)
        self.grid252 = None                     # consumed
        self.play(FadeIn(self.yz_dice), run_time=0.6)
        self.wait(0.3)
        # the five plain dice take the five colors
        self.play(*[d.body.animate.set_fill(col, opacity=1.0)
                    for d, col in zip(self.yz_dice, DIE_COLORS)], run_time=0.8)
        self.wait(0.3)
        # swap die-1 and die-2 pips, then back — identical dice, so nothing really
        # changes (→ one arrangement).
        d1, d2 = self.yz_dice[0], self.yz_dice[1]
        # raise the moving pips so they stay ON TOP of the other die's body while
        # they arc across (otherwise d1's pips end up hidden behind d2)
        d1.pips.set_z_index(10)
        d2.pips.set_z_index(10)
        off = d2.get_center() - d1.get_center()
        self.play(d1.pips.animate.shift(off), d2.pips.animate.shift(-off),
                  path_arc=PI, run_time=0.8)
        self.play(d1.pips.animate.shift(-off), d2.pips.animate.shift(off),
                  path_arc=PI, run_time=0.8)
        d1.pips.set_z_index(0)
        d2.pips.set_z_index(0)
        self.wait(0.8)

    # ── d. 33333 → 12345, roll permutations, then fill the 120-straight grid ────
    @subscene
    def straight_120(self):
        self._setup_straight_120()              # owns s120 (yz_dice carried in)
        dice = self.yz_dice          # 5 colored dice showing 3 3 3 3 3
        morph_dice(self, dice, [1, 2, 3, 4, 5], run_time=0.7)
        self.wait(0.2)
        # morph through two permutations of 1-5…
        for perm in ([3, 1, 4, 5, 2], [4, 2, 5, 1, 3]):
            morph_dice(self, dice, perm, run_time=0.7)
            self.wait(0.15)
        # …then morph back to 1 2 3 4 5
        morph_dice(self, dice, [1, 2, 3, 4, 5], run_time=0.7)
        self.wait(0.2)
        # shrink the straight into the grid's top-left, then fill the rest out
        self.play(ReplacementTransform(dice, self.s120[0]), run_time=1.0)
        self.yz_dice = None                     # consumed
        self.play(LaggedStart(*[FadeIn(g) for g in self.s120[1:]],
                              lag_ratio=0.01), run_time=1.6)
        self.wait(0.8)

    # ── e. 240 straights vs 6 yahtzees → ~40x ──────────────────────────────────
    @subscene
    def straights_vs_yahtzees(self):
        # owns s240*/six_yz/labels; s120 carried in. d's 120 (1-5) straights
        # relocate into the TOP half (same 120, same order); the 2-6 bottom half
        # and the 6 yahtzees appear alongside.
        self._setup_straights_vs()
        self.play(
            ReplacementTransform(self.s120, self.s240_top),
            FadeIn(self.s240_bot),
            FadeIn(self.six_yz),
            run_time=1.2,
        )
        self.s120 = None                        # consumed
        self.play(FadeIn(self.s240_label), FadeIn(self.six_label), run_time=0.5)
        self.wait(1.0)

    # ── f. frequency table: example combo (colored pips) + # of ways ───────────
    @subscene
    def frequency_table(self):
        self._setup_frequency()                 # owns freq_* (s240/six_yz carried)
        self.play(FadeOut(self.s240), FadeOut(self.six_yz),
                  FadeOut(self.s240_label), FadeOut(self.six_label), run_time=0.6)
        self.play(FadeIn(self.freq_title, shift=DOWN * 0.2), run_time=0.5)
        self.play(LaggedStart(*[FadeIn(r, shift=RIGHT * 0.2)
                                for r in self.freq_rows],
                              lag_ratio=0.15, run_time=1.8))
        self.wait(1.0)
