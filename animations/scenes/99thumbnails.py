from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *


class Thumbnails(YahtzeeScene):
    """Scene 99 — YouTube thumbnails (static title cards, NOT animated).

    BLANK scaffold. Add ONE `@subscene` per thumbnail; each builds a STATIC
    composition and `add`s it (no `self.play`). The cyan `BG_COLOR` is applied
    automatically by `YahtzeeScene`. Model the GIST on battleship's
    `00thumbnail.py` (big bold title/number + a prop), but on `BpkScene` with a
    subscene per thumbnail. Pull props from `assets/` (e.g. `get_die`,
    `get_scorecard`) and text through `crisp_text` (build small, `.scale()` up).

    Grab the PNG per thumbnail with:
        render 99a --frames "1.0" --extract        # 1080p, from the render loop
    or, for a true 4K export (like battleship):
        <repo>/.venv/bin/manim -s -qk 99thumbnails.py Thumbnails   # whole-scene last frame

    Template (uncomment + fill in — remember to import any assets you use):

        # a : main thumbnail
        @subscene
        def main(self):
            title = crisp_text("YAHTZEE", font_size=20, color=BLACK,
                               weight="BOLD").scale(4).to_edge(UP, buff=0.8)
            self.add(title)
            # …+ a prop (dice / scorecard) — see assets/

    NB numbers on a thumbnail are still SOURCED, never invented (see the
    numbers-are-the-product rule).
    """

    def setup_scene(self):
        pass

    # a : (placeholder) — replace with the first real thumbnail (see docstring).
    #     One @subscene per thumbnail; build a static composition and self.add() it.
    @subscene
    def main(self):
        pass
