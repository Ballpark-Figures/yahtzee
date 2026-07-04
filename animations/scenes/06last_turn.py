from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import DiceBoard, morph_dice
from bpkfigures.histogram import get_histogram


# ── Scene 06 — the last turn ──────────────────────────────────────────────────
# For EACH box: if it's the only box left open on the last turn, what's the
# optimal 3-roll play, its P(success) and its EV? All numbers ignore the Yahtzee
# bonus and the 63 bonus (isolated single box). Every figure is SOURCED from
# math/scene06_last_turn_numbers.py (run it to reproduce):
#   top mean count 2.1 ; count dist 0..5 = 6.49/23.63/34.40/25.04/9.12/1.33 %
#   Yahtzee 4.6% ; Full House 36.6% / EV 9.15 ; Lg Str 26.5% / 10.61
#   Sm Str 61.6% / 18.48 ; Chance 23.33 ; 4-kind 27.7% / 5.61 ; 3-kind 71.2% / 15.19
#   chance per-die 3.5 -> 4.25 -> 4.667 ; 4-kind keep-1s 52% vs keep-6s 23%
#
# 38 subscenes (a..z, za..zl). Two script beats are voiceover-only (the
# "keep 56/456" summary and the "play perfectly" concept) and get NO subscene.

# scores[0..5] Ones..Sixes | 6 3ofK | 7 4ofK | 8 FH | 9 SmS | 10 LgS |
# 11 Yahtzee | 12 Chance | 13 yahtzee-bonus.  Yahtzee = 0 so no bonus is ever
# available; top sum 59 < 63 so no top bonus either.
SAMPLE = [3, 6, 9, 8, 15, 18,  18, 20, 25, 30, 40, 0, 22,  0]

# scorecard row indices (asset order: Yahtzee=11, Chance=12)
R_THREES = 2
R_3KIND, R_4KIND, R_FH, R_SMS, R_LGS, R_YAH, R_CHANCE = 6, 7, 8, 9, 10, 11, 12

# ── layout ────────────────────────────────────────────────────────────────────
# The 4-column card is ~6.5 wide (about half the frame), so its leftmost
# non-clipping center is ~-3.65 — it can't reach the usual LEFT_SC (-4.74).
CARD_C   = [-3.65, 0, 0]
COL4_W   = 1.4
# dice: tighter + shifted right so the wide card fits (script: "remove space to
# left of first die and right of last die")
DICE_AX  = 3.8
DICE_DX  = 1.15
LINE_X   = (0.2, 6.9)            # guide lines span the dice gutter, clear of card


class LastTurn(YahtzeeScene):
    """Scene 06 — the endgame, box by box. Subscene bodies are ANIMATION ONLY;
    each builds what it owns via a _setup_* helper, then plays."""

    def setup_scene(self):
        # Follows talking head THD — nothing on screen at frame 0.
        pass

    # ── shared build helpers ─────────────────────────────────────────────────
    def _setup_card(self):
        # Keep the normal 3 columns (labels/values/summary) + the new 4th info
        # column. A box is open through the whole scene, so the top bar reads as
        # "in progress" (blue), not the red "missed the 63 bonus".
        self.card = get_scorecard(
            SAMPLE, center=CARD_C,
            fourth_column=True, fourth_width=COL4_W,
        )

    def _setup_board(self, start=(1, 2, 3, 4, 5)):
        self.board = DiceBoard(area_x=DICE_AX, slot_dx=DICE_DX, line_x=LINE_X)
        self.board.place_initial(list(start))

    # ── a) intro: bring in the card, walk the boxes ──────────────────────────
    @subscene
    def intro(self):
        self._setup_card()
        in_rt, hl_rt = 1.1, 3.0

        # enter with a SHIFT (never an opacity fade — corrupts the card)
        self.card.shift(LEFT * 11)
        self.add(self.card)
        self.play(self.card.animate.move_to(CARD_C), run_time=in_rt)

        # "Highlight boxes one at a time" — a flash walking down every row.
        self.card.highlight_rows(self, list(range(13)), pulse=True,
                                 lag_ratio=0.18, run_time=hl_rt)

    # ── b) top section: roll for threes (2 -> 3 -> 4 of them) ─────────────────
    @subscene
    def top_threes(self):
        self._setup_board()
        clear_rt, in_rt, roll_rt, keep_rt, score_rt = 0.7, 0.8, 0.7, 0.5, 1.1

        # clear just the Threes box; hold it highlighted for the section
        self.card.transition(self, {R_THREES: None}, run_time=clear_rt)
        self.play(FadeIn(self.board.lines), *[FadeIn(d) for d in self.board.dice],
                  run_time=in_rt)

        self.play(*self.board.first_roll([3, 3, 2, 4, 6]), run_time=roll_rt)   # 2 threes
        self.wait(0.2)
        self.play(*self.board.keep([0, 1]), run_time=keep_rt)
        self.play(*self.board.roll_rest([3, 5, 1]), run_time=roll_rt)          # 3 threes
        self.wait(0.2)
        self.play(*self.board.keep([0, 1, 2]), run_time=keep_rt)
        self.play(*self.board.roll_rest([3, 6]), run_time=roll_rt)             # 4 threes
        self.wait(0.3)

        self.card.upper(self, self.board.dice, 3)     # score four 3s -> 12
        self.wait(0.3)

    # ── c) histogram of "how many of the value", then park it in column 4 ─────
    @subscene
    def top_histogram(self):
        self._setup_hist()
        in_rt, move_rt = 1.0, 1.1

        # big + readable on the right: standing bars, 0-5 labels, % on each bar
        self.play(FadeIn(self.hist, shift=UP * 0.3),
                  FadeIn(self.hist_avg1, shift=UP * 0.3), run_time=in_rt)
        self.wait(0.5)

        # park it in the TOP of column 4; drop the %; swap the Avg for a big
        # 2-line version below the mini-histogram (live region tracks the card)
        top_c, _w, top_h = self.card.col4_region(range(6))
        mini_c = top_c + UP * top_h * 0.24
        self.hist_avg2.move_to(top_c + DOWN * top_h * 0.28)
        self.play(
            self.hist.animate.scale(0.30).move_to(mini_c),
            FadeOut(self.hist.bar_labels),
            FadeOut(self.hist_avg1),
            FadeIn(self.hist_avg2),
            run_time=move_rt,
        )
        self.wait(0.2)

    def _setup_hist(self):
        # count distribution of the target value after 3 rolls (SOURCED)
        counts = {0: 6.49, 1: 23.63, 2: 34.40, 3: 25.04, 4: 9.12, 5: 1.33}
        self.hist = get_histogram(
            None, counts=counts, is_vertical=False,      # standing bars
            center=[3.6, -0.2, 0], width=4.4, height=3.0,
            bar_color=ACCENT_FILL, x_tick_step=1,         # label every value 0..5
            x_axis_label="number obtained",
            bar_labels="percent", bar_label_font_size=22,
        )
        # big single-line caption for the on-the-right display
        self.hist_avg1 = crisp_text("Avg 2.1", font_size=32, color=BLACK,
                                    font=FONT, weight="BOLD")
        self.hist_avg1.next_to(self.hist, DOWN, buff=0.3)
        # large 2-line caption for once it's parked in column 4
        self.hist_avg2 = VGroup(
            crisp_text("Avg", font_size=30, color=BLACK, font=FONT, weight="BOLD"),
            crisp_text("2.1", font_size=36, color=BLACK, font=FONT, weight="BOLD"),
        ).arrange(DOWN, buff=0.06)
