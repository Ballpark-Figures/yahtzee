from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from manim import config as MCFG            # real frame is 16x9 (y-radius 4.5)
from config import *
from assets.dice import get_die


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

    One `@subscene` per thumbnail; each builds a STATIC composition and `add`s
    it (no `self.play`). The cyan `BG_COLOR` is applied by `YahtzeeScene`. Style
    modelled on battleship's `00thumbnail.py` (big bold black number up top + a
    prop below, subtle gradient bg + bold digit stroke to survive YouTube's
    downscale/JPEG pass) — but in the NEW brand FONT (Inter, via `crisp_text`).

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
    @subscene
    def positions(self):
        # ---- anti-artifact tunables (mirror battleship's 00thumbnail) --------
        BG_GRAD_LIGHT = 0.06   # how far the top of the bg leans toward WHITE
        BG_GRAD_DARK  = 0.05   # how far the bottom of the bg leans toward BLACK
        NUM_STROKE_W  = 3.0    # extra black stroke on the digits (bolds them)

        # ---- the number (sourced) -------------------------------------------
        # 258,521,977,812,672 = scene 1's final reveal, the "~259 trillion
        # possible positions" (01intro.py gt_final; Script.md row 01 col 2).
        NUM_POSITIONS = "258,521,977,812,672"
        NUM_WIDTH = 13.0

        # ---- the dice (12345, colored pips) ---------------------------------
        DIE_SIZE_THUMB = 2.4    # big prop dice
        DICE_BUFF      = 0.45
        DICE_Y         = -1.75
        DIE_BORDER_W   = 4.0    # thumbnail-only border thickness (default is 2.0)

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

        # the number: big, bold, black, in the brand FONT (Inter). Center it
        # vertically between the top of the frame and the top of the dice.
        number = crisp_text(NUM_POSITIONS, font_size=48, color=BLACK)
        number.scale_to_fit_width(NUM_WIDTH)
        num_y = (MCFG.frame_y_radius + dice.get_top()[1]) / 2
        number.move_to([0, num_y, 0])
        if NUM_STROKE_W > 0:
            number.set_stroke(BLACK, width=NUM_STROKE_W, opacity=1.0)

        self.add(bg, number, dice)
