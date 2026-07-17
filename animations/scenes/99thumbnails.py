from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from manim import config as MCFG            # real frame is 16x9 (y-radius 4.5)
from config import *
from assets.dice import get_die, DIE_COLORS, SLOT_DX, ascend_and_flash

# Scene 2's large-straight staircase rises `step` per die over a SLOT_DX gap
# (assets/dice.py `ascend_and_flash`), so its slope is ASCEND_STEP / SLOT_DX.
# Read the step from the function's own default so the thumbnail can't drift.
ASCEND_STEP = ascend_and_flash.__kwdefaults__["step"]


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

        # the number: big, bold, black, in the brand FONT (Inter). Center it
        # vertically between the top of the frame and the top of the dice.
        number = crisp_text(NUM_POSITIONS, font_size=48, color=BLACK)
        number.scale_to_fit_width(NUM_WIDTH)
        num_y = (MCFG.frame_y_radius + dice.get_top()[1]) / 2
        number.move_to([0, num_y, 0])
        if NUM_STROKE_W > 0:
            number.set_stroke(BLACK, width=NUM_STROKE_W, opacity=1.0)

        self.add(bg, number, dice)

    # b : same number, "large-straight" styling — colored BODIES (red->blue,
    #     black pips) stepped along a diagonal, like scene 03's straight
    @thumbnail
    def straight(self):
        # ---- anti-artifact tunables (mirror battleship's 00thumbnail) --------
        BG_GRAD_LIGHT = 0.06
        BG_GRAD_DARK  = 0.05
        NUM_STROKE_W  = 3.0

        # ---- the number (sourced, same as subscene a) -----------------------
        NUM_POSITIONS = "258,521,977,812,672"
        NUM_WIDTH = 13.0

        # ---- the dice (12345, colored BODIES on a diagonal) -----------------
        # Colored-die mode (body_color) => black pips + border, bodies red->blue
        # per DIE_COLORS — the identity coloring of scene 03's large straight.
        # SLOPE matches scene 2's large-straight staircase: ascend_and_flash steps
        # each die up 0.2 over a SLOT_DX horizontal gap (assets/dice.py), so the
        # diagonal's dy/dx = 0.2 / SLOT_DX. Derive DICE_DY from DICE_DX so the
        # thumbnail's tilt is that exact slope (not a made-up one).
        DIE_SIZE_THUMB = 1.7
        DICE_DX        = 2.5     # rightward step per die (spacing; free thumbnail choice)
        DICE_DY        = DICE_DX * (ASCEND_STEP / SLOT_DX)   # upward step → scene-2 slope
        DICE_CENTER_Y  = -1.3

        bg = vertical_gradient_panel(
            interpolate_color(BG_COLOR, WHITE, BG_GRAD_LIGHT),
            interpolate_color(BG_COLOR, BLACK, BG_GRAD_DARK),
        )

        dice = VGroup(*[
            get_die(v, size=DIE_SIZE_THUMB, body_color=DIE_COLORS[v - 1])
            for v in range(1, 6)
        ])
        for i, d in enumerate(dice):             # step each die along the diagonal
            d.move_to([i * DICE_DX, i * DICE_DY, 0])
        dice.move_to([0, DICE_CENTER_Y, 0])

        # number centered vertically between the frame top and the dice's top
        number = crisp_text(NUM_POSITIONS, font_size=48, color=BLACK)
        number.scale_to_fit_width(NUM_WIDTH)
        num_y = (MCFG.frame_y_radius + dice.get_top()[1]) / 2
        number.move_to([0, num_y, 0])
        if NUM_STROKE_W > 0:
            number.set_stroke(BLACK, width=NUM_STROKE_W, opacity=1.0)

        self.add(bg, number, dice)
