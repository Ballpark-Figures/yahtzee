from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.dice import get_die
from bpkfigures.scroll_list import ScrollList

# ── Dummy data (NOT real numbers — placeholder to eyeball the motion + column
# behaviour). Shape matches scene 10: (box, points, sample dice, avg game pts).
# Each row is a caller-built 4-column mobject, exercising the generic
# "items are Mobjects" path exactly the way scene 10 will. ──────────────────────
DATA = [
    ("Yahtzee",        50, [4, 4, 4, 4, 4], 268.0),
    ("Four Sixes",     24, [6, 6, 6, 6, 1], 262.5),
    ("Four Fives",     20, [5, 5, 5, 5, 2], 259.0),
    ("Large Straight", 40, [2, 3, 4, 5, 6], 257.5),
    ("Four Fours",     16, [4, 4, 4, 4, 3], 256.0),
    ("Four Threes",    12, [3, 3, 3, 3, 5], 254.0),
    ("Full House",     25, [5, 5, 5, 2, 2], 252.0),
    ("Small Straight", 30, [1, 2, 3, 4, 6], 250.5),
    ("Three Sixes",    18, [6, 6, 6, 2, 4], 249.0),
    ("Chance",         19, [2, 3, 4, 4, 6], 247.5),
    ("Three Fives",    15, [5, 5, 5, 1, 3], 246.0),
    ("Two Sixes",      12, [6, 6, 1, 3, 4], 244.0),
    ("Four Ones",       4, [1, 1, 1, 1, 5], 240.0),
    ("Bad Roll",       19, [2, 3, 4, 4, 6], 238.0),
]

# Fixed column anchors (so columns would line up if rows weren't scaled).
BOX_X, PTS_X, DICE_X, AVG_X = -3.7, -1.5, 1.0, 3.7   # box=left edge, avg=right edge
FS = FONT_SIZE_SM


def make_row(box, pts, dice_vals, avg):
    lab = crisp_text(box, font_size=FS)
    pt = crisp_text(str(pts), font_size=FS)
    dice = VGroup(*[get_die(v, size=0.30) for v in dice_vals]).arrange(RIGHT, buff=0.05)
    av = crisp_text(f"{avg:.1f}", font_size=FS, color=ACCENT_FILL)
    lab.move_to([BOX_X + lab.width / 2, 0, 0])     # left edge pinned
    pt.move_to([PTS_X, 0, 0])                      # centred
    dice.move_to([DICE_X, 0, 0])                   # centred
    av.move_to([AVG_X - av.width / 2, 0, 0])       # right edge pinned
    return VGroup(lab, pt, dice, av)


ROWS = [make_row(*d) for d in DATA]
LABELS = [d[0] for d in DATA]


class ScrollTest(YahtzeeScene):
    def setup_scene(self):
        self.wheel = ScrollList(ROWS, keys=LABELS, focus=0, radius=3)

    @subscene
    def appear(self):
        self.add(self.wheel)                       # enter() fades in dice-safe
        self.play(self.wheel.enter(), run_time=1.0)

    @subscene
    def step_down(self):
        self.play(self.wheel.scroll_to(4), run_time=1.5)          # by index

    @subscene
    def jump_to_label(self):
        self.play(self.wheel.scroll_to("Chance"), run_time=2.0)   # by label

    @subscene
    def spin_back(self):
        self.play(self.wheel.scroll_to(0), run_time=2.5)          # long spin

    @subscene
    def leave(self):
        self.play(self.wheel.exit(), run_time=1.0)
