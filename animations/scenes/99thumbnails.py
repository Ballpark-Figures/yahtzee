from pathlib import Path
import math
import sys

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from manim import config as MCFG            # real frame is 16x9 (y-radius 4.5)
from config import *
from assets.dice import get_die, DIE_COLORS, DIE_BEIGE, SLOT_DX, ascend_and_flash

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

    # a : 259-trillion positions — scene 1's final number + colored-pip 1-2-3-4-5
    @thumbnail
    def positions(self):
        # ---- anti-artifact tunables (mirror battleship's 00thumbnail) --------
        BG_GRAD_LIGHT = 0.06   # how far the top of the bg leans toward WHITE
        BG_GRAD_DARK  = 0.05   # how far the bottom of the bg leans toward BLACK

        # ---- the dice (12345, colored pips) ---------------------------------
        DIE_SIZE_THUMB = 2.4    # big prop dice
        DICE_BUFF      = 0.45
        DICE_Y         = -1.75
        DIE_BORDER_W   = 6.0    # thumbnail-only border thickness (default is 2.0)

        # subtle gradient background over the flat cyan (anti-ringing)
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

        # "All" / number / "Positions", centered above the dice
        block = self._number_block(dice.get_top()[1])
        self.add(bg, block, dice)

    # b : same number, "large-straight" styling — colored BODIES (black pips)
    #     stepped along a diagonal. THE ANIMATION's flash colours (scene 2's
    #     large_straight: RED/ORANGE/YELLOW/GREEN/BLUE).
    @thumbnail
    def straight(self):
        self._straight_thumb([get_die(v, size=THUMB_DIE_SIZE, body_color=ANIM_COLORS[v - 1])
                              for v in range(1, 6)])

    # c : identical to b EXCEPT the palette — scene 03's straight DIE_COLORS
    #     (softer hexes) instead of the pure animation colours.
    @thumbnail
    def straight_alt(self):
        self._straight_thumb([get_die(v, size=THUMB_DIE_SIZE, body_color=DIE_COLORS[v - 1])
                              for v in range(1, 6)])

    # d : HALF-coloured — dice before the transition use b's animation colours,
    #     dice after are default (beige); the transition die fades its own colour
    #     -> beige across a line perpendicular to the line of dice. Here die 3.
    @thumbnail
    def straight_half(self):
        self._half_thumb(3)

    # e : same idea, transition one die LATER — die 3 stays fully yellow, die 4
    #     is the gradient (green -> beige); die 5 default.
    @thumbnail
    def straight_half4(self):
        self._half_thumb(4)

    def _half_thumb(self, k):
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
        self._straight_thumb(dice)

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

    def _number_block(self, dice_top_y):
        """The label block shared by EVERY thumbnail: the big sourced number with
        'All' above and 'Positions' below (smaller, centered). Returns the VGroup,
        centered horizontally and vertically between the frame top and dice_top_y.

        The number 258,521,977,812,672 = scene 1's final reveal, the "~259 trillion
        possible positions" (01intro.py gt_final; Script.md row 01 col 2)."""
        NUM_POSITIONS = "258,521,977,812,672"
        NUM_WIDTH     = 13.0
        NUM_STROKE_W  = 3.0
        LABEL_FRAC    = 0.45   # 'All'/'Positions' height ÷ the number's height
        LABEL_STROKE  = 1.5
        LABEL_BUFF    = 0.22   # gap between the labels and the number

        number = crisp_text(NUM_POSITIONS, font_size=48, color=BLACK)
        number.scale_to_fit_width(NUM_WIDTH)
        number.set_stroke(BLACK, width=NUM_STROKE_W, opacity=1.0)

        all_lbl, pos_lbl = (crisp_text(w, font_size=48, color=BLACK)
                            for w in ("All", "Positions"))
        for lbl in (all_lbl, pos_lbl):
            lbl.scale_to_fit_height(number.height * LABEL_FRAC)
            lbl.set_stroke(BLACK, width=LABEL_STROKE, opacity=1.0)

        block = VGroup(all_lbl, number, pos_lbl).arrange(DOWN, buff=LABEL_BUFF)
        block.move_to([0, (MCFG.frame_y_radius + dice_top_y) / 2, 0])
        return block

    def _straight_thumb(self, dice):
        """Shared builder for the diagonal large-straight thumbnails (b/c/d): the
        frames differ ONLY in the per-die colouring passed in. Steps the dice along
        scene 2's slope, thickens every border to match subscene a, and adds the bg
        + the centered number."""
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

        # "All" / number / "Positions", centered above the dice
        block = self._number_block(group.get_top()[1])
        self.add(bg, block, group)
