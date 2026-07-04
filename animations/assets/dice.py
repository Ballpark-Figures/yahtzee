from pathlib import Path
import sys
import random

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from manim import *
from config import *
import numpy as np

# ── Die appearance ───────────────────────────────────────────────────────────
DIE_BEIGE = "#ECE1C4"
DIE_SIZE  = 0.95

# value -> color for pip_coloring: 1 red, 2 orange ... 6 purple (rainbow).
# Darker/deeper shades so they read well on the beige die face.
PIP_COLORS = {
    1: "#C0392B",   # deep red
    2: "#D35400",   # burnt orange
    3: "#C9A200",   # dark gold (yellow that's visible on beige)
    4: "#1E8449",   # forest green
    5: "#1F618D",   # steel blue
    6: "#6C3483",   # deep purple
}

# Body-fill colors for the "colored dice" mode (separate from pip_coloring):
# the WHOLE FACE takes one of these — five distinct colors, one per die —
# while the pips and border stay BLACK. Colors are value-independent, so any
# color can sit on any face value, in any order. Bright enough that black pips
# read clearly on the colored face.
DIE_COLORS = [
    "#E74C3C",   # red
    "#E67E22",   # orange
    "#F1C40F",   # yellow
    "#2ECC71",   # green
    "#3498DB",   # blue
]

# pip positions on a 3x3 grid: gx in {-1,0,1} (cols), gy in {-1,0,1} (+1 = top)
PIP_GRID = {
    "TL": (-1, 1),  "TR": (1, 1),
    "ML": (-1, 0),  "MR": (1, 0),
    "BL": (-1, -1), "BR": (1, -1),
    "C":  (0, 0),
}
# which grid positions light up for each face
PIP_FACES = {
    1: ["C"],
    2: ["TL", "BR"],
    3: ["TL", "C", "BR"],
    4: ["TL", "TR", "BL", "BR"],
    5: ["TL", "TR", "C", "BL", "BR"],
    6: ["TL", "TR", "ML", "MR", "BL", "BR"],
}


class Die(VGroup):
    """A rounded beige die showing `value` (1-6) as black pips.

    The die keeps a *fixed* pool of 7 pips (one per possible grid position) and
    `set_value` only repositions them and toggles their opacity. Their identity
    never changes, so Manim's render optimization keeps tracking them while the
    die moves and scales inside an animation.
    """

    def __init__(self, value=1, size=DIE_SIZE, pip_color=BLACK,
                 pip_coloring=False, body_color=None, **kwargs):
        super().__init__(**kwargs)
        self.size = size
        self.pip_color = pip_color
        # When True, the border and pips take the value's rainbow color (see
        # PIP_COLORS) and re-tint whenever the face changes; otherwise they stay
        # `pip_color`/black.
        self.pip_coloring = pip_coloring
        # "Colored dice" mode: a value-independent body fill (see DIE_COLORS).
        # None -> the default beige face. This is independent of pip_coloring;
        # the pips/border stay black regardless of the body color.
        self.body_color = body_color
        self.body = RoundedRectangle(
            width=size, height=size, corner_radius=size * 0.18,
            fill_color=body_color if body_color is not None else DIE_BEIGE,
            fill_opacity=1.0,
            stroke_color=BLACK, stroke_width=2.0,
        )
        self.pips = VGroup()
        self._pips = {}
        for key in PIP_GRID:
            dot = Dot(radius=size * 0.085, color=pip_color)
            self._pips[key] = dot
            self.pips.add(dot)
        self.add(self.body, self.pips)
        self.set_value(value)

    def _accent_color(self):
        """The current border/pip color: value-based when pip_coloring is on."""
        if self.pip_coloring:
            return PIP_COLORS[self.value]
        return self.pip_color

    def set_pip_coloring(self, on=True):
        """Toggle value-based coloring and re-tint the border + pips in place."""
        self.pip_coloring = on
        self._apply_accent()
        return self

    def set_body_color(self, color):
        """Set the body fill ("colored dice" mode). `color=None` restores beige.
        The pips and border are untouched (they stay black)."""
        self.body_color = color
        self.body.set_fill(
            color if color is not None else DIE_BEIGE, opacity=1.0)
        return self

    def _apply_accent(self):
        color = self._accent_color()
        self.body.set_stroke(color=color)
        for dot in self._pips.values():
            dot.set_color(color)

    def set_opacity(self, opacity, family=True):
        """Fade ONLY the visible content: the body (fill + border) and the pips
        that are currently lit. The die keeps a fixed pool of 7 pips with the
        unused ones at opacity 0; a plain VGroup.set_opacity would lift those
        hidden pips to `opacity` too, so a fade made all 7 pips appear. Keep the
        inactive pips hidden so fading a die never reveals phantom pips."""
        self.body.set_opacity(opacity)
        active = set(PIP_FACES[self.value])
        for key, dot in self._pips.items():
            dot.set_opacity(opacity if key in active else 0.0)
        return self

    def set_value(self, value):
        self.value = int(value)
        w = self.body.width
        c = self.body.get_center()
        spacing = w * 0.28
        pip_d = w * 0.17
        active = set(PIP_FACES[self.value])

        for key, dot in self._pips.items():
            gx, gy = PIP_GRID[key]
            dot.scale_to_fit_width(pip_d)
            dot.move_to(c + np.array([gx * spacing, gy * spacing, 0.0]))
            dot.set_opacity(1.0 if key in active else 0.0)
        self._apply_accent()
        return self


def get_die(value=1, size=DIE_SIZE, **kwargs):
    return Die(value=value, size=size, **kwargs)


def morph_dice(scene, dice, values, run_time=0.6):
    """Animate each die changing its face to the given value (pips rearrange)."""
    anims = []
    for d, v in zip(dice, values):
        target = d.copy()
        target.set_value(v)
        anims.append(Transform(d, target))
    scene.play(*anims, run_time=run_time)
    for d, v in zip(dice, values):
        d.set_value(v)   # re-sync identity + .value after the Transform


# ── Showcase motions (used by scoring animations) ────────────────────────────
_RAINBOW = [RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE]


def _rainbow_color(t):
    n = len(_RAINBOW)
    x = (t % 1.0) * n
    i = int(x) % n
    return interpolate_color(_RAINBOW[i], _RAINBOW[(i + 1) % n], x - int(x))


class JumpSpin(Animation):
    """Spin a die a full turn while it grows toward the camera and back (a scale
    bump, like the roll). With `rainbow=True` the body cycles colors mid-spin."""

    def __init__(self, die, *, bump=0.4, turns=1, rainbow=False, phase=0.0,
                 run_time=1.0, **kwargs):
        self.bump    = bump
        self.turns   = turns
        self.rainbow = rainbow
        self.phase   = phase
        super().__init__(die, run_time=run_time, **kwargs)

    def begin(self):
        self.center = self.mobject.get_center()
        self.base   = self.mobject.copy()   # absolute reference, no accumulating state
        super().begin()

    def interpolate_mobject(self, alpha):
        d = self.mobject
        d.become(self.base)
        d.rotate(self.turns * TAU * alpha)
        d.scale(1 + self.bump * np.sin(np.pi * alpha))
        d.move_to(self.center)
        if self.rainbow:
            d.body.set_fill(_rainbow_color(self.phase + 2 * alpha), opacity=1.0)

    def finish(self):
        super().finish()
        if self.rainbow:
            self.mobject.body.set_fill(DIE_BEIGE, opacity=1.0)


class FlashFill(Animation):
    """Pulse a die's body fill to `color` and bump its size, keeping the black
    pips and border intact (only the face color flashes, not the whole die)."""

    def __init__(self, die, color, *, scale_factor=1.18, run_time=0.6, **kwargs):
        self.flash_color  = ManimColor(color)   # accept hex strings or ManimColor
        self.scale_factor = scale_factor
        self.base_fill    = die.body.get_fill_color()
        super().__init__(die, run_time=run_time, **kwargs)

    def begin(self):
        self.base = self.mobject.copy()         # absolute reference, no accumulating state
        super().begin()

    def interpolate_mobject(self, alpha):
        d = self.mobject
        pulse = np.sin(np.pi * alpha)           # 0 -> 1 -> 0, so it returns to base
        d.become(self.base)
        d.scale(1 + (self.scale_factor - 1) * pulse)
        d.body.set_fill(interpolate_color(self.base_fill, self.flash_color, pulse), opacity=1.0)


def jump_and_spin(scene, dice, *, rainbow=False, bump=0.4, turns=1, run_time=1.0):
    """Play JumpSpin on all dice at once."""
    scene.play(*[JumpSpin(d, bump=bump, turns=turns, rainbow=rainbow,
                          phase=i / len(dice)) for i, d in enumerate(dice)],
               run_time=run_time)


def reorder_dice(scene, dice_in_slot_order, *, band=3, y=None, run_time=0.7):
    """Slide dice into slots 0,1,2,... in the given left-to-right order. `y`
    overrides the band's height (used by the centered-dice presentation)."""
    yy = BAND_YS[band] if y is None else y
    scene.play(*[d.animate.move_to([slot_x(i), yy, 0])
                 for i, d in enumerate(dice_in_slot_order)],
               run_time=run_time)


def reindex_dice(dice, new_order):
    """Rewrite the dice list IN PLACE so it matches `new_order` (the dice in their
    current left-to-right slot order). After a rearrange we keep the dice where
    they are and just relabel them — the die now in slot 0 becomes die 0, etc. —
    so nothing has to move back afterwards."""
    dice[:] = list(new_order)
    return dice


def ascend_and_flash(scene, dice_in_order, colors, *, band=3, y=None, step=0.2, run_time=0.9):
    """Stagger dice into an ascending staircase (left/low → right/high), then
    flash them left-to-right in `colors`. `y` overrides the band's base height
    (used by the centered-dice presentation)."""
    yy = BAND_YS[band] if y is None else y
    k = len(dice_in_order)
    moves = []
    for i, d in enumerate(dice_in_order):
        moves.append(d.animate.move_to([slot_x(i), yy + (i - (k - 1) / 2) * step, 0]))
    scene.play(*moves, run_time=run_time * 0.55)
    scene.play(
        LaggedStart(*[FlashFill(d, c, scale_factor=1.2)
                      for d, c in zip(dice_in_order, colors)], lag_ratio=0.25),
        run_time=run_time,
    )


class SpinShrink(Animation):
    """Spin a die toward `target` while shrinking it to nothing. With
    rainbow=True the body cycles colors as it goes."""

    def __init__(self, die, target, *, turns=2, rainbow=False, phase=0.0,
                 run_time=1.0, **kwargs):
        self.target  = np.array(target, dtype=float)
        self.turns   = turns
        self.rainbow = rainbow
        self.phase   = phase
        super().__init__(die, run_time=run_time, **kwargs)

    def begin(self):
        self.start = self.mobject.get_center()
        self.base  = self.mobject.copy()
        super().begin()

    def interpolate_mobject(self, alpha):
        d = self.mobject
        d.become(self.base)
        d.rotate(self.turns * TAU * alpha)
        d.scale(max(1 - alpha, 1e-3))
        d.move_to(self.start + (self.target - self.start) * alpha)
        if self.rainbow:
            d.body.set_fill(_rainbow_color(self.phase + 2 * alpha), opacity=1.0)


def spin_into(scene, dice, target, *, rainbow=False, turns=2, run_time=1.0):
    """Spin copies of the dice toward `target` while shrinking them to nothing.
    The original dice stay put."""
    copies = [d.copy() for d in dice]
    for c in copies:
        scene.add(c)
    scene.play(
        *[SpinShrink(c, target, turns=turns, rainbow=rainbow, phase=i / len(copies))
          for i, c in enumerate(copies)],
        run_time=run_time,
    )
    scene.remove(*copies)


def spin_into_anim(scene, dice, target, *, rainbow=False, turns=2):
    """Like spin_into, but RETURNS (copies, AnimationGroup) instead of playing it,
    so the caller can run the dice-into-box flight concurrently with something
    else (e.g. a counter tick). Remove `copies` from the scene when done."""
    copies = [d.copy() for d in dice]
    for c in copies:
        scene.add(c)
    anim = AnimationGroup(*[SpinShrink(c, target, turns=turns, rainbow=rainbow,
                                       phase=i / len(copies))
                            for i, c in enumerate(copies)])
    return copies, anim


def respawn_dice(scene, dice, values, *, band=3, run_time=0.5):
    """Fade faded-out dice back in at their slots with new values."""
    for i, (d, v) in enumerate(zip(dice, values)):
        d.set_value(v)
        d.move_to(slot_point(band, i))
    scene.play(*[FadeIn(d) for d in dice], run_time=run_time)


# ── Roll animation ───────────────────────────────────────────────────────────
class RollDie(Animation):
    """Toss a die from its current spot to `target`, landing on `final_value`.

    The die grows toward the camera in mid-flight (a scale bump) and the face
    flickers through random values that slow down and settle the instant it
    lands.
    """

    def __init__(self, die, target, final_value, *, bump=0.4, n_flips=16,
                 flip_ease=0.8, start_size=None, end_size=None,
                 run_time=1.0, rate_func=smooth, **kwargs):
        self.target = np.array(target, dtype=float)
        self.final_value = int(final_value)
        self.bump = bump
        # Optional start/end base sizes: the die's base width is interpolated
        # from start_size to end_size across the toss (the mid-flight bump rides
        # on top). Either left None falls back to the die's size at begin().
        self.start_size = start_size
        self.end_size = end_size

        # Flip schedule: flips are dense early and sparse late, so the face
        # changes quickly at first then slows as it settles. flip i fires at
        # alpha = 1 - (1 - i/n)**flip_ease, so the last flip (i = n) lands
        # exactly at alpha = 1.0 — the face keeps changing right up until the
        # die lands, and only that final flip locks in the final value.
        # flip_ease controls the slowdown: 1.0 = uniform spacing (no settle),
        # smaller = more front-loaded (the old sqrt curve was 0.5, which left
        # the die sitting on its 2nd-to-last value for a full 0.25 of the toss).
        self.flip_alphas = []
        self.flip_values = []
        prev = None
        for i in range(1, n_flips + 1):
            self.flip_alphas.append(1 - (1 - i / n_flips) ** flip_ease)
            if i == n_flips:
                v = self.final_value
            else:
                v = random.choice([x for x in range(1, 7) if x != prev])
            self.flip_values.append(v)
            prev = v

        super().__init__(die, run_time=run_time, rate_func=rate_func, **kwargs)

    def begin(self):
        self.start_point = self.mobject.get_center()
        base = self.mobject.size
        self._size0 = self.start_size if self.start_size is not None else base
        self._size1 = self.end_size if self.end_size is not None else base
        super().begin()

    def _value_at(self, alpha):
        v = self.flip_values[0]
        for a, val in zip(self.flip_alphas, self.flip_values):
            if alpha >= a:
                v = val
            else:
                break
        return v

    def interpolate_mobject(self, alpha):
        die = self.mobject
        center = self.start_point + (self.target - self.start_point) * alpha
        base = self._size0 + (self._size1 - self._size0) * alpha
        desired = base * (1 + self.bump * np.sin(np.pi * alpha))
        cur_w = die.body.width
        if cur_w > 1e-6:
            die.scale(desired / cur_w)
        die.move_to(center)
        die.set_value(self._value_at(alpha))

    def finish(self):
        super().finish()
        die = self.mobject
        if die.body.width > 1e-6:
            die.scale(self._size1 / die.body.width)
        die.move_to(self.target)
        die.set_value(self.final_value)


# ── Playfield geometry ───────────────────────────────────────────────────────
# Screen is 16 x 9: top edge +4.5, bottom -4.5. The three guide lines sit at
# 1/4, 1/2 and 3/4 of the way down.
LINE_YS = [2.25, 0.0, -2.25]            # top, middle, bottom
# Band centers, indexed 0..3 from the bottom:
#   0 = below the bottom line (start), 1 = bottom..middle,
#   2 = middle..top, 3 = above the top line
BAND_YS = [-3.375, -1.125, 1.125, 3.375]

DICE_AREA_X = 3.0                       # center x of the dice row (right of scorecard)
SLOT_DX     = 1.4                       # horizontal spacing between the 5 slots


def slot_x(slot):
    return DICE_AREA_X + (slot - 2) * SLOT_DX


def slot_point(band, slot):
    return np.array([slot_x(slot), BAND_YS[band], 0.0])


# ── Keep-DECISION illustration (the shared "push a keep forward" convention) ──
# Kept dice push forward one band (into the left slots); the reroll dice stay on
# the SAME band, shifted into the slots to the RIGHT of the kept. Stateless +
# deterministic by keep-set, so calling repeatedly MORPHS one keep straight into
# another (unlike keep()/roll_rest(), which advance a real roll).
#
# BAND-PER-REROLL CONVENTION — `base_band` encodes WHICH reroll it is (dice roll
# UP one band per roll: band1 = first roll, band2 = second, band3 = final):
#   • FIRST reroll  → base_band=1: dice at band 1, keep pushes up to band 2
#                     (2 rerolls of headroom → the decision sits LOWER).
#   • SECOND reroll → base_band=2: dice at band 2, keep pushes up to band 3
#     ("last roll")   (the top → the decision sits HIGHER).
# `point` is the (band, slot) -> position function (module slot_point by default;
# a DiceBoard passes its own instance geometry).
def show_keep_anims(dice, keep_idxs, base_band, point=slot_point):
    keep_set = set(keep_idxs)
    n = len(dice)
    kept = [i for i in range(n) if i in keep_set]
    others = [i for i in range(n) if i not in keep_set]
    target = {}
    for s, i in enumerate(kept):
        target[i] = point(base_band + 1, s)
    for j, i in enumerate(others):
        target[i] = point(base_band, len(kept) + j)
    return [dice[i].animate.move_to(target[i]) for i in range(n)]


def regroup_anims(dice, band, point=slot_point):
    """Anims to line all dice up in slot order at `band` (undo a keep split)."""
    return [dice[i].animate.move_to(point(band, i)) for i in range(len(dice))]


def roll_lines(x_left=-1.5, x_right=7.5, color=WHITE, opacity=0.45, stroke_width=2.0):
    lines = VGroup()
    for y in LINE_YS:
        ln = Line([x_left, y, 0], [x_right, y, 0],
                  stroke_color=color, stroke_width=stroke_width)
        ln.set_opacity(opacity)
        lines.add(ln)
    return lines


# ── Dice board: manages 5 dice and the roll/keep flow ────────────────────────
class DiceBoard:
    """Holds 5 dice plus the guide lines and produces the standard
    roll / keep / roll-the-rest animations.

    Bands move upward each round:
        place_initial -> band 0 (below the bottom line)
        first_roll    -> band 1 (above the bottom line)
        keep + roll_rest moves the whole group up one band each round.

    Every method returns a list of animations to hand to `self.play(*...)`.
    """

    def __init__(self, n=5, size=DIE_SIZE, area_x=DICE_AREA_X, slot_dx=SLOT_DX,
                 line_x=None):
        # area_x / slot_dx let a scene tighten + shift the dice row (scene 06
        # narrows the gutter to make room for the scorecard's 4th column). They
        # default to the module constants, so every other scene is unchanged.
        # line_x=(x_left, x_right) sets the guide-line span; None keeps the
        # default extent.
        self.area_x = area_x
        self.slot_dx = slot_dx
        self.dice = [Die(value=1, size=size) for _ in range(n)]
        self.lines = roll_lines() if line_x is None else roll_lines(x_left=line_x[0], x_right=line_x[1])
        self.band = 0
        self.slot = {i: i for i in range(n)}   # die index -> slot (0..4)
        self.kept = []
        self._pending = None

    def _slot_x(self, slot):
        return self.area_x + (slot - 2) * self.slot_dx

    def _slot_point(self, band, slot):
        return np.array([self._slot_x(slot), BAND_YS[band], 0.0])

    def all_mobjects(self):
        return VGroup(self.lines, *self.dice)

    def place_initial(self, values):
        for i, d in enumerate(self.dice):
            d.set_value(values[i])
            d.move_to(self._slot_point(0, i))
            self.slot[i] = i
        self.band = 0
        self.kept = []

    def first_roll(self, values):
        anims = [RollDie(d, self._slot_point(1, self.slot[i]), values[i])
                 for i, d in enumerate(self.dice)]
        self.band = 1
        return anims

    def keep(self, keep_indices):
        """Send kept dice up into the next band's first slots, and shift the
        rest into the last slots of the current band. Follow with roll_rest()."""
        keep_set = set(keep_indices)
        nb = self.band + 1
        kept = sorted(keep_set, key=lambda i: self.slot[i])
        others = sorted((i for i in range(len(self.dice)) if i not in keep_set),
                        key=lambda i: self.slot[i])

        new_slot = {}
        anims = []
        for s, i in enumerate(kept):
            new_slot[i] = s
            anims.append(self.dice[i].animate.move_to(self._slot_point(nb, s)))
        for j, i in enumerate(others):
            s = len(kept) + j
            new_slot[i] = s
            anims.append(self.dice[i].animate.move_to(self._slot_point(self.band, s)))

        self.slot = new_slot
        self.kept = kept
        self._pending = dict(nb=nb, others=others)
        return anims

    def roll_rest(self, values):
        """Roll the non-kept dice up into the next band's last slots.
        `values` is aligned with the non-kept dice in left-to-right order."""
        nb = self._pending["nb"]
        others = self._pending["others"]
        anims = [RollDie(self.dice[i], self._slot_point(nb, self.slot[i]), values[j])
                 for j, i in enumerate(others)]
        self.band = nb
        return anims

    # ── Keep-DECISION illustration (no reroll) — see show_keep_anims above for
    #    the convention + the band-per-reroll rule. These wrap it with the board's
    #    OWN geometry (so they work with a custom area_x/slot_dx layout).
    def show_keep(self, keep_idxs, base_band=None):
        if base_band is None:
            base_band = self.band
        return show_keep_anims(self.dice, keep_idxs, base_band, self._slot_point)

    def regroup(self, band):
        return regroup_anims(self.dice, band, self._slot_point)
