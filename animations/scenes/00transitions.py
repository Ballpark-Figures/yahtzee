from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *

# ── look (title-card tunables) ────────────────────────────────────────────────
# Build the text UNDER the ~24 crisp_text wrap threshold, then .scale() up — so a
# long title ("Multiplayer Yahtzee") never silently line-breaks (see the crisp_text
# note in yahtzee/CLAUDE.md).
BASE_FS     = 20           # title built at this, then scaled
TITLE_SCALE = 3.0          # the title's final size (× the base)
TEXT_COLOR  = BLACK        # title colour on the cyan background

# The six cards are the subscenes below, in video order (each comment notes the
# Part # it corresponds to — the number is no longer shown on screen).


class Transitions(YahtzeeScene):
    """Scene 00 — the part-title cards between scene groups.

    Each card starts ON SCREEN (just the part title, centred), holds, then FADES
    out to reveal the blank background for the cut into the next scene. One subscene
    per part, in video order:

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

    def _card(self, name):
        """The title, centred. Built small, scaled up (no wrap)."""
        return crisp_text(name, font_size=BASE_FS, color=TEXT_COLOR,
                          weight="BOLD").scale(TITLE_SCALE).move_to(ORIGIN)

    def _show(self, name, *, hold, run_time):
        """Title is on screen from the start, holds `hold`s (read time — tuned per
        card to its voiceover), then FADES out over `run_time` to reveal the blank
        background. hold + run_time are separate knobs on purpose: one is pacing, one
        is the fade."""
        card = self._card(name)
        self.add(card)
        self.wait(hold)
        self.play(FadeOut(card), run_time=run_time)

    # a : Part 0 — The Math
    @subscene
    def math(self):
        self._show("The Math", hold=1.5, run_time=1.0)

    # b : Part −1 — The Endgame
    @subscene
    def endgame(self):
        self._show("The Endgame", hold=1.5, run_time=1.0)

    # c : Part −2 — The Middlegame
    @subscene
    def middlegame(self):
        self._show("The Middlegame", hold=1.5, run_time=1.0)

    # d : Part −3 — The Opening
    @subscene
    def opening(self):
        self._show("The Opening", hold=1.5, run_time=1.0)

    # e : Part 1 — 2-Player Yahtzee
    @subscene
    def two_player(self):
        self._show("2-Player Yahtzee", hold=1.5, run_time=1.0)

    # f : Part 2 — Multiplayer Yahtzee
    @subscene
    def multiplayer(self):
        self._show("Multiplayer Yahtzee", hold=1.5, run_time=1.0)
