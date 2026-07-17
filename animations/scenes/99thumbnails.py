from pathlib import Path
from itertools import combinations_with_replacement
import math
import sys

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from manim import config as MCFG            # real frame is 16x9 (y-radius 4.5)
from config import *
from assets.dice import (get_die, DIE_COLORS, DIE_BEIGE, PIP_COLORS, SLOT_DX,
                         ascend_and_flash)

# Scene 2's large-straight staircase rises `step` per die over a SLOT_DX gap
# (assets/dice.py `ascend_and_flash`), so its slope is ASCEND_STEP / SLOT_DX.
# Read the step from the function's own default so the thumbnail can't drift.
ASCEND_STEP = ascend_and_flash.__kwdefaults__["step"]

# Diagonal-thumbnail die size (matches subscene a) and scene 2's large_straight
# flash colours (scorecard.large_straight). ANIM_COLORS uses the raw palette on
# purpose — these ARE the animation's colours (lint warns; intentional).
THUMB_DIE_SIZE = 2.4
ANIM_COLORS = [RED, ORANGE, YELLOW, GREEN, BLUE]


def vertical_gradient_panel(top_color, bottom_color, width=16.0, height=9.0,
                            n_strips=140):
    """A smooth vertical gradient as a stack of thin strips (from battleship's
    00thumbnail). Stacked strips render a guaranteed top->bottom gradient
    regardless of Manim's gradient-direction quirks; used as a near-flat
    background so JPEG ringing around the text has no large flat field to be
    visible against. (Local copy, matching battleship — promote to bpkfigures
    if a third thumbnail wants it.)"""
    strips = VGroup()
    h = height / n_strips
    for i in range(n_strips):
        a = i / (n_strips - 1)
        y = height / 2.0 - (i + 0.5) * h
        strips.add(
            Rectangle(
                width=width,
                height=h * 1.03,            # slight overlap kills seam lines
                stroke_width=0,
                fill_color=interpolate_color(top_color, bottom_color, a),
                fill_opacity=1.0,
            ).move_to([0, y, 0])
        )
    return strips


# ── the 252 dice-sets from scene 1 (for the dice-field thumbnails) ────────────
# Fit + row-balance the 252-set grid to the frame with equal margins — replicates
# scene 1's _fit_equal_margins / _balance_rows (01intro.py) so it reads the same.
_FIELD_MARGIN = 0.15
_FIELD_W = 16 - 2 * _FIELD_MARGIN     # 15.7
_FIELD_H = 9 - 2 * _FIELD_MARGIN      # 8.7


def _fit_field(group, rows):
    group.scale_to_fit_width(_FIELD_W)
    if group.height > _FIELD_H:
        group.scale_to_fit_height(_FIELD_H)
    group.move_to(ORIGIN)
    if rows >= 2 and group.height < _FIELD_H - 1e-3:   # stretch ROW positions to fill H
        factor = _FIELD_H / group.height
        cy = group.get_center()[1]
        for sub in group:
            x, y, z = sub.get_center()
            sub.move_to([x, cy + (y - cy) * factor, z])
    return group


def _near_text(g, lines, margin):
    """True if dice-set `g`'s bbox comes within `margin` of ANY text line's bbox."""
    gl, gr, gb, gt = g.get_left()[0], g.get_right()[0], g.get_bottom()[1], g.get_top()[1]
    for L in lines:
        ll, lr = L.get_left()[0] - margin, L.get_right()[0] + margin
        lb, lt = L.get_bottom()[1] - margin, L.get_top()[1] + margin
        if not (gr < ll or gl > lr or gt < lb or gb > lt):
            return True
    return False


class Thumbnails(YahtzeeScene):
    """Scene 99 — YouTube thumbnails (static title cards, NOT animated).

    One `@thumbnail` per thumbnail; each builds a STATIC composition and `add`s
    it (no `self.play`). `@thumbnail` (not `@subscene`) makes each frame INDEPENDENT
    — the framework renders it from a clean, empty frame with no carry-over from the
    previous one — so keep the video's normal base (`YahtzeeScene`, which applies the
    cyan `BG_COLOR`). Style modelled on battleship's `00thumbnail.py` (big bold black
    number up top + a prop below, subtle gradient bg + bold digit stroke to survive
    YouTube's downscale/JPEG pass) — but in the NEW brand FONT (Inter, via `crisp_text`).

    Grab the PNG per thumbnail with:
        render 99a                                 # 4K PNG (manim -s -qk), the upload asset
        render 99a --fast                          # quick low-res PNG to check layout
    Scene 99 auto-renders as a still image (no --thumb needed — the 99 slot is
    reserved for thumbnails). The PNG lands (and its path prints) under
    media/images/99thumbnails/.

    NB numbers on a thumbnail are still SOURCED, never invented (see the
    numbers-are-the-product rule).
    """

    def setup_scene(self):
        pass

    # NOTE a–e are the PLAIN thumbnails (number only); f–j are the SAME five WITH
    # the "All … Positions" text. Each composition is a `_*_thumb(..., labels)`
    # builder so the two forms never drift apart.

    # a : 259-trillion positions — scene 1's final number + colored-pip 1-2-3-4-5
    @thumbnail
    def positions(self):
        self._positions_thumb(labels=False)

    # b : "large-straight" styling — colored BODIES (black pips) stepped along a
    #     diagonal, THE ANIMATION's flash colours (scene 2 large_straight).
    @thumbnail
    def straight(self):
        self._straight_thumb(self._anim_dice(), labels=False)

    # c : identical to b EXCEPT the palette — scene 03's straight DIE_COLORS.
    @thumbnail
    def straight_alt(self):
        self._straight_thumb(self._dc_dice(), labels=False)

    # d : HALF-coloured straight, transition at die 3 (its colour -> beige).
    @thumbnail
    def straight_half(self):
        self._half_thumb(3, labels=False)

    # e : half-coloured, transition one die LATER — die 3 fully yellow, die 4 the
    #     gradient (green -> beige), die 5 default.
    @thumbnail
    def straight_half4(self):
        self._half_thumb(4, labels=False)

    # ── f–j: the same five, WITH the "All … Positions" text ────────────────────
    # f : a + labels
    @thumbnail
    def positions_labeled(self):
        self._positions_thumb(labels=True)

    # g : b + labels
    @thumbnail
    def straight_labeled(self):
        self._straight_thumb(self._anim_dice(), labels=True)

    # h : c + labels
    @thumbnail
    def straight_alt_labeled(self):
        self._straight_thumb(self._dc_dice(), labels=True)

    # i : d + labels
    @thumbnail
    def straight_half_labeled(self):
        self._half_thumb(3, labels=True)

    # j : e + labels
    @thumbnail
    def straight_half4_labeled(self):
        self._half_thumb(4, labels=True)

    # k : j but WITHOUT the "All" — only "Positions" below the number
    @thumbnail
    def straight_half4_positions(self):
        self._half_thumb(4, labels="positions")

    # ── l–q: the 252 dice-sets from scene 1 filling the frame, text centered ────
    # l : + centered number (no words)
    @thumbnail
    def field_plain(self):
        self._dice_field_thumb(labels=False)

    # m : + centered 'All' / number / 'Positions'
    @thumbnail
    def field_labeled(self):
        self._dice_field_thumb(labels=True)

    # n : + centered number / 'Positions'
    @thumbnail
    def field_positions(self):
        self._dice_field_thumb(labels="positions")

    # o–q : l–n but with the 6 value COLOURS on the die BODIES (black pips/border)
    # o : number only
    @thumbnail
    def field_body_plain(self):
        self._dice_field_thumb(labels=False, colored_body=True)

    # p : All / number / Positions
    @thumbnail
    def field_body_labeled(self):
        self._dice_field_thumb(labels=True, colored_body=True)

    # q : number / Positions
    @thumbnail
    def field_body_positions(self):
        self._dice_field_thumb(labels="positions", colored_body=True)

    def _dice_field_thumb(self, labels, colored_body=False):
        """The 252 distinct 5-dice outcomes from scene 1 filling the frame, with the
        number block centered vertically; any dice-set that comes within KEEP_OUT of
        the text is removed so the words sit in clear space. `colored_body` puts the
        6 value colours on the die BODIES (black pips/border) instead of on the pips."""
        BG_GRAD_LIGHT = 0.06
        BG_GRAD_DARK  = 0.05
        DIE_SIZE = 0.24        # scene 1's 252-quint die size
        DIE_BUFF = 0.025       # scene 1's k=5 within-group buff
        KEEP_OUT = 0.3         # remove dice-sets within this margin of the text

        bg = vertical_gradient_panel(
            interpolate_color(BG_COLOR, WHITE, BG_GRAD_LIGHT),
            interpolate_color(BG_COLOR, BLACK, BG_GRAD_DARK),
        )

        # 252 sets of 5 dice, canonical order, 21×12 down the rows, fit to the frame —
        # matches scene 1's 252 grid (flow_order="dr"). Pips coloured by value, OR
        # (colored_body) the value colour on the body with black pips.
        def _die(v):
            if colored_body:
                return get_die(v, size=DIE_SIZE, body_color=PIP_COLORS[v])
            return get_die(v, size=DIE_SIZE, pip_coloring=True)

        combos = list(combinations_with_replacement(range(1, 7), 5))   # 252, canonical
        groups = VGroup(*[
            VGroup(*[_die(v) for v in combo]).arrange(RIGHT, buff=DIE_BUFF)
            for combo in combos
        ])
        groups.arrange_in_grid(rows=21, cols=12, buff=(DIE_BUFF * 4, DIE_BUFF * 4),
                               flow_order="dr")
        _fit_field(groups, rows=21)

        # Shrink the number just enough that its keep-out never reaches the leftmost
        # / rightmost dice columns, so those full columns survive. flow_order='dr'
        # fills column-major (21 per column): first 21 = left column, last 21 = right.
        gl = list(groups)
        col_left_inner  = max(g.get_right()[0] for g in gl[:21])    # left col's right edge
        col_right_inner = min(g.get_left()[0]  for g in gl[-21:])   # right col's left edge
        max_half = min(-col_left_inner, col_right_inner) - KEEP_OUT - 0.02
        num_width = min(13.0, 2 * max_half)

        # centered-vertically number block; drop the dice-sets it crowds
        block = self._number_block(0, labels, num_width=num_width)
        block.move_to(ORIGIN)
        lines = list(block.submobjects) if isinstance(block, VGroup) else [block]
        kept = VGroup(*[g for g in groups if not _near_text(g, lines, KEEP_OUT)])

        self.add(bg, kept, block)

    # ── shared builders ────────────────────────────────────────────────────────
    def _anim_dice(self):
        """1..5 with the scene-2 animation body colours (RED..BLUE)."""
        return [get_die(v, size=THUMB_DIE_SIZE, body_color=ANIM_COLORS[v - 1])
                for v in range(1, 6)]

    def _dc_dice(self):
        """1..5 with scene 03's DIE_COLORS body palette."""
        return [get_die(v, size=THUMB_DIE_SIZE, body_color=DIE_COLORS[v - 1])
                for v in range(1, 6)]

    def _half_thumb(self, k, labels):
        """Half-coloured straight: dice 1..k-1 fully in their animation colour, die
        k the gradient (its own colour -> beige), dice k+1..5 default beige."""
        dice = []
        for v in range(1, 6):
            if v < k:
                dice.append(get_die(v, size=THUMB_DIE_SIZE, body_color=ANIM_COLORS[v - 1]))
            elif v == k:
                dice.append(self._gradient_die(v, THUMB_DIE_SIZE, ANIM_COLORS[v - 1], DIE_BEIGE))
            else:
                dice.append(get_die(v, size=THUMB_DIE_SIZE))             # default beige
        self._straight_thumb(dice, labels)

    def _positions_thumb(self, labels):
        """Subscene a's composition: colored-pip 1-2-3-4-5 in a row under the number
        block. `labels` toggles the 'All'/'Positions' text."""
        BG_GRAD_LIGHT = 0.06   # how far the top of the bg leans toward WHITE
        BG_GRAD_DARK  = 0.05   # how far the bottom of the bg leans toward BLACK
        DIE_SIZE_THUMB = 2.4    # big prop dice
        DICE_BUFF      = 0.45
        DICE_Y         = -1.75
        DIE_BORDER_W   = 6.0    # thumbnail-only border thickness (default is 2.0)

        bg = vertical_gradient_panel(
            interpolate_color(BG_COLOR, WHITE, BG_GRAD_LIGHT),
            interpolate_color(BG_COLOR, BLACK, BG_GRAD_DARK),
        )
        # 1-2-3-4-5 with per-value rainbow pips/border (pip_coloring convention)
        dice = VGroup(*[
            get_die(value=v, size=DIE_SIZE_THUMB, pip_coloring=True)
            for v in range(1, 6)
        ]).arrange(RIGHT, buff=DICE_BUFF)
        dice.move_to([0, DICE_Y, 0])
        for d in dice:                       # thicker border (keeps pip_coloring color)
            d.body.set_stroke(width=DIE_BORDER_W)
        block = self._number_block(dice.get_top()[1], labels)
        self.add(bg, block, dice)

    def _gradient_die(self, value, size, c_from, c_to, *, band=1.0, n_strips=90):
        """A die whose interior goes `c_from` (dice-2 side) -> `c_to` (dice-4 side),
        the transition CONCENTRATED in a narrow `band` (die units) around a line
        perpendicular to the line of dice.

        Built as colour strips (tilted to the dice-line angle) clipped to the die
        shape with Intersection, placed BEHIND a transparent-fill body so the black
        border + pips stay crisp on top. We clip strips rather than use manim's
        plain gradient fill, which smears colour around the rounded-rect perimeter
        (that put yellow in the bottom-right and stretched the blend over the whole
        die)."""
        c_from, c_to = ManimColor(c_from), ManimColor(c_to)   # DIE_BEIGE is a hex str
        d = get_die(value, size=size)
        body = d.body
        clip = body.copy().set_fill(WHITE, opacity=1.0).set_stroke(width=0)
        backing = body.copy().set_fill(c_to, opacity=1.0).set_stroke(width=0)  # hides gaps
        body.set_fill(opacity=0.0)               # transparent interior; keep the border
        ctr = body.get_center()
        theta = math.atan2(ASCEND_STEP, SLOT_DX)  # dice-line angle → perpendicular divide
        u = np.array([math.cos(theta), math.sin(theta), 0.0])   # gradient axis
        # Cover the die's FULL projection onto u — the tilted corners reach beyond
        # size/2 (~size*0.68 at this angle), so size alone left a gap (beige backing
        # showing) at the bottom-left corner. 1.5 clears it with margin.
        span = size * 1.5
        strip_w = span / n_strips
        overlay = VGroup()
        for i in range(n_strips):
            t = -span / 2 + (i + 0.5) * strip_w   # position along the gradient axis
            a = min(1.0, max(0.0, (t + band / 2) / band))       # 0 = c_from .. 1 = c_to
            col = interpolate_color(c_from, c_to, a)
            strip = Rectangle(width=strip_w * 1.6, height=size * 1.6,
                              stroke_width=0, fill_color=col, fill_opacity=1.0)
            strip.rotate(theta).move_to(ctr + t * u)
            piece = Intersection(strip, clip, fill_color=col, fill_opacity=1.0,
                                 stroke_width=0)
            overlay.add(piece)
        d.add_to_back(overlay)                    # behind the (transparent) body + pips
        d.add_to_back(backing)                    # beige backing behind the strips
        return d

    def _number_block(self, dice_top_y, labels, num_width=13.0):
        """The number block shared by every thumbnail: the big sourced number,
        optionally wrapped by 'All' above and/or 'Positions' below (smaller). Returns
        the mobject, centered horizontally and vertically between the frame top and
        dice_top_y. `labels` selects which words: False/None (none), True/'both'
        (All + Positions), or 'positions' (only 'Positions'). `num_width` sets the
        number's width (the dice-field thumbnails shrink it to clear the outer dice).

        The number 258,521,977,812,672 = scene 1's final reveal, the "~259 trillion
        possible positions" (01intro.py gt_final; Script.md row 01 col 2)."""
        NUM_POSITIONS = "258,521,977,812,672"
        NUM_STROKE_W  = 3.0
        LABEL_FRAC    = 0.58   # 'All'/'Positions' height ÷ the number's height
        LABEL_STROKE  = 1.8
        LABEL_GAP     = 0.4    # gap from the DIGIT body to each label

        number = crisp_text(NUM_POSITIONS, font_size=48, color=BLACK)
        number.scale_to_fit_width(num_width)
        number.set_stroke(BLACK, width=NUM_STROKE_W, opacity=1.0)

        show_all = labels in (True, "both")
        show_pos = labels in (True, "both", "positions")

        def _label(word, ref_y, direction):
            lbl = crisp_text(word, font_size=48, color=BLACK)
            lbl.scale_to_fit_height(number.height * LABEL_FRAC)
            lbl.set_stroke(BLACK, width=LABEL_STROKE, opacity=1.0)
            # Balance labels around the DIGITS, not the bbox: the commas hang below
            # the baseline, so measuring to the bbox bottom would push 'Positions'
            # further from the number than 'All'. Use the digit tops / the baseline
            # (bottom of the first digit '2') so the gaps match.
            lbl.next_to(np.array([0, ref_y, 0]), direction, buff=LABEL_GAP)
            return lbl

        parts = []
        if show_all:
            parts.append(_label("All", number.get_top()[1], UP))
        parts.append(number)
        if show_pos:
            parts.append(_label("Positions", number[0].get_bottom()[1], DOWN))
        block = VGroup(*parts) if len(parts) > 1 else number

        block.move_to([0, (MCFG.frame_y_radius + dice_top_y) / 2, 0])
        return block

    def _straight_thumb(self, dice, labels):
        """Shared builder for the diagonal large-straight thumbnails: the frames
        differ ONLY in the per-die colouring passed in (and `labels`). Steps the dice
        along scene 2's slope, thickens every border to match subscene a, and adds
        the bg + the number block."""
        # ---- anti-artifact tunables (mirror battleship's 00thumbnail) --------
        BG_GRAD_LIGHT = 0.06
        BG_GRAD_DARK  = 0.05
        DIE_BORDER_W  = 6.0                       # match subscene a's border thickness

        # ---- diagonal geometry ----------------------------------------------
        # Size/spacing match subscene a (size 2.4, buff 0.45). SLOPE matches scene 2's
        # large-straight staircase: ascend_and_flash steps each die up by ASCEND_STEP
        # over a SLOT_DX gap (assets/dice.py), so dy/dx = ASCEND_STEP / SLOT_DX.
        DICE_DX       = THUMB_DIE_SIZE + 0.45     # spacing = size + buff, like 99a
        DICE_DY       = DICE_DX * (ASCEND_STEP / SLOT_DX)   # upward step → scene-2 slope
        DICE_CENTER_Y = -1.5

        bg = vertical_gradient_panel(
            interpolate_color(BG_COLOR, WHITE, BG_GRAD_LIGHT),
            interpolate_color(BG_COLOR, BLACK, BG_GRAD_DARK),
        )

        group = VGroup(*dice)
        for i, d in enumerate(dice):             # step each die along the diagonal
            d.move_to([i * DICE_DX, i * DICE_DY, 0])
            d.body.set_stroke(width=DIE_BORDER_W)  # thicken border to match a
        group.move_to([0, DICE_CENTER_Y, 0])

        block = self._number_block(group.get_top()[1], labels)
        if labels:
            # Equalize three vertical gaps: frame-top↔'All', 'Positions'↔die-4 top,
            # and die-1 bottom↔frame-bottom. Solve for the block-top T and a dice
            # shift s (die-4 = dice[3], the 2nd-highest; die-1 = dice[0], lowest):
            #   G1 = fy - T ; G2 = (T - H) - die4_top ; G3 = die1_bot + fy
            #   set G1 = G2 = G3 = G  →  G = (2·fy - H - die4_top + die1_bot) / 3
            fy       = MCFG.frame_y_radius
            H        = block.height
            die4_top = dice[3].get_top()[1]
            die1_bot = dice[0].get_bottom()[1]
            G = (2 * fy - H - die4_top + die1_bot) / 3
            group.shift(UP * (G - fy - die1_bot))          # die1_bot → G - fy
            block.shift(UP * ((fy - G) - block.get_top()[1]))  # block top → fy - G
        self.add(bg, block, group)
