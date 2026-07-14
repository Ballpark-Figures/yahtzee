from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *

# ── look (title-card tunables) ────────────────────────────────────────────────
# Build the text UNDER the ~24 crisp_text wrap threshold, then .scale() up — so a
# long title ("Multiplayer Yahtzee") never silently line-breaks (see the crisp_text
# note in yahtzee/CLAUDE.md).
BASE_FS     = 20            # both lines built at this, then scaled
NUM_SCALE   = 1.8          # "Part N" final size (× the base)
TITLE_SCALE = 3.0          # the title line final size (× the base)
GAP         = 0.4          # buff between the two lines
TEXT_COLOR  = BLACK        # title colour on the cyan background

# Negative parts count backward (the game's structure); "−" is the typographic
# minus the rest of the video uses (cf. scene 12 `_sgn`), not a hyphen. The six
# cards are the subscenes below, in video order.


class Transitions(YahtzeeScene):
    """Scene 00 — the part-title cards between scene groups.

    Each card starts ON SCREEN (two centred lines: Part # / title), holds, then
    slides UP off the top to reveal the blank background for the cut into the next
    scene. One subscene per part, in video order:

      a math        — Part 0  : The Math
      b endgame     — Part −1 : The Endgame
      c middlegame  — Part −2 : The Middlegame
      d opening     — Part −3 : The Opening
      e two_player  — Part 1  : 2-Player Yahtzee
      f multiplayer — Part 2  : Multiplayer Yahtzee
    """

    def setup_scene(self):
        # Nothing persists between cards — each subscene builds its own.
        pass

    def _card(self, num, name):
        """The two-line title group, centred. Built small, scaled up (no wrap)."""
        line1 = crisp_text(num, font_size=BASE_FS, color=TEXT_COLOR,
                           weight="BOLD").scale(NUM_SCALE)
        line2 = crisp_text(name, font_size=BASE_FS, color=TEXT_COLOR,
                           weight="BOLD").scale(TITLE_SCALE)
        return VGroup(line1, line2).arrange(DOWN, buff=GAP).move_to(ORIGIN)

    def _show(self, num, name, *, hold, run_time):
        """Card is on screen from the start, holds `hold`s (read time — tuned per
        card to its voiceover), then slides UP off the top over `run_time` (the exit
        motion) to reveal blank. hold + run_time are separate knobs on purpose: one
        is pacing, one is motion."""
        card = self._card(num, name)
        self.add(card)
        self.wait(hold)
        off = config.frame_y_radius + card.height / 2 + 0.5   # clear the top edge
        self.play(card.animate.shift(UP * off), run_time=run_time)

    # a : Part 0 — The Math
    @subscene
    def math(self):
        self._show("Part 0", "The Math", hold=1.5, run_time=1.0)

    # b : Part −1 — The Endgame
    @subscene
    def endgame(self):
        self._show("Part −1", "The Endgame", hold=1.5, run_time=1.0)

    # c : Part −2 — The Middlegame
    @subscene
    def middlegame(self):
        self._show("Part −2", "The Middlegame", hold=1.5, run_time=1.0)

    # d : Part −3 — The Opening
    @subscene
    def opening(self):
        self._show("Part −3", "The Opening", hold=1.5, run_time=1.0)

    # e : Part 1 — 2-Player Yahtzee
    @subscene
    def two_player(self):
        self._show("Part 1", "2-Player Yahtzee", hold=1.5, run_time=1.0)

    # f : Part 2 — Multiplayer Yahtzee
    @subscene
    def multiplayer(self):
        self._show("Part 2", "Multiplayer Yahtzee", hold=1.5, run_time=1.0)
