from bpkfigures.scene import *

CENTER_SC   = [0, 0, 0]
LEFT_SC     = [-4.74, 0, 0]

SCORE_GREEN = "#1A7A1A"
AVG_GREEN   = "#146014"   # slightly darker green for the scene-04 "avg points" readouts
SCORE_RED   = "#A60E00"
CARD_FILL   = "#F7F2E7"   # cream scorecard surface
CARD_ACCENT = "#BE2716"   # scorecard header + Total bars (red, midway SCORE_RED↔ACCENT_RED)
STRIPE_FILL = "#ECE3CE"   # zebra row shading
GRID_LINE   = "#A89C82"   # light interior grid lines

SCORECARD_FONT_SIZE = 30.0


class YahtzeeScene(BpkScene):
    def construct(self):
        self.camera.background_color = BG_COLOR
        super().construct()
