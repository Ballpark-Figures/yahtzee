from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import get_die, FlashFill
from bpkfigures.card import get_card, card_behind


# ── the numbers (ALL SOURCED — see math/scene09_top_bonus_numbers.py) ──────────
# Every value below is expected top-bonus points = 35 * p_top_bonus_after, read
# from the solved state_properties shards via state_explorer. NOT recomputed here.
#   BASE_EV : top-bonus EV at the empty start card         (35 * 0.68122 = 23.84)
#   TABLE   : EV if on turn 1 you score `count` dice of `number` in its top box.
#             rows keyed by COUNT (0..4), each a list over numbers 1..6.
BASE_EV = 23.8
TABLE = {
    0: [16.4, 10.5,  4.3,  0.9,  0.1,  0.0],
    1: [18.5, 15.2, 10.3,  5.4,  1.8,  0.3],
    2: [20.5, 19.4, 17.4, 14.4, 10.9,  6.4],
    3: [22.9, 23.6, 23.7, 23.4, 23.1, 22.4],
    4: [24.5, 27.4, 29.2, 30.3, 31.1, 31.9],
}
COUNTS_TOP_DOWN = [0, 1, 2, 3, 4]      # row 0 sits at the TOP (per the user)

# ── layout ─────────────────────────────────────────────────────────────────────
CARD_L = LEFT_SC                        # scorecard sits left the whole scene

# beat b: 6 rows x 3 dice, on the right
GRID_CX, GRID_CY = 2.6, 0.4
GRID_DSZ = 0.5
GRID_ROW_DY = 0.62
GRID_COL_DX = 0.62

# beat c/d: the hanging containers
U        = 0.15                         # points -> screen units
TOP_Y    = 1.5                          # the common "full / 63" line
BG_X0    = 0.85
BG_DX    = 0.82
CW       = 0.52                         # container inner width
BG_LABEL_Y = -1.65
FILL_BLUE  = ACCENT_FILL
FILL_GOLD  = ACCENT_GOLD                # the "extra" that overflows / slides

# beat e-i: the table
TB_X0, TB_DX = 0.95, 0.78               # data col 0 center, col spacing
TB_HEAD_Y    = 1.55
TB_DY        = 0.62
TB_CW, TB_CH = 0.74, 0.56
EV_Y         = 2.45

NEUTRAL_C = ManimColor(CARD_FILL)
GREEN_C   = ManimColor(SCORE_GREEN)
RED_C     = ManimColor(SCORE_RED)


def _cell_color(v):
    """Diverging fill: neutral cream at BASE_EV, -> green toward 35, -> red toward 0."""
    if v >= BASE_EV:
        t = min((v - BASE_EV) / (35 - BASE_EV), 1.0)
        return interpolate_color(NEUTRAL_C, GREEN_C, t)
    t = min((BASE_EV - v) / BASE_EV, 1.0)
    return interpolate_color(NEUTRAL_C, RED_C, t)


class TopBonus(YahtzeeScene):
    """Scene 09 — the top bonus.

    Scorecard sits LEFT the whole scene. The right side cycles through: the
    "3-of-each = 63" dice grid (b), the hanging-container graph (c, d), then the
    turn-1 EV table (e-i). Follows animated scene 08 (so a brings the card IN);
    precedes talking-head THG (so it may end with the full table on screen).

      top_section     — empty card in from left; highlight the top section
      three_of_each   — 6x3 dice, sum rows/cols, merge to 63
      empty_containers— clear; draw the 6 hanging open-top containers
      fill_containers — the "3 of each fills it; surplus pours over" demo
      table_empty     — clear; empty 6x5 EV table + the turn-0 EV (23.8)
      fill_3          — reveal the count-3 row
      fill_4          — reveal the count-4 row
      fill_2          — reveal count-2; highlight 2 ones, then 2 sixes
      fill_1_0        — reveal count-1, then count-0; highlight the 0 row
    """

    def setup_scene(self):
        # Scene 08 (animated) leaves the screen empty; a animates the card in.
        pass

    # ══ builders ════════════════════════════════════════════════════════════════
    def _setup_card(self):
        self.card = get_scorecard(center=CARD_L)      # empty card

    def _setup_grid(self):
        cols = 3
        rows = 6
        x0 = GRID_CX - (cols - 1) / 2 * GRID_COL_DX
        y0 = GRID_CY + (rows - 1) / 2 * GRID_ROW_DY
        self.grid_rows = []                            # list per value of [dice]
        dice = VGroup()
        for r in range(rows):                          # r=0 -> value 1 (top)
            val = r + 1
            row_dice = []
            for c in range(cols):
                d = get_die(val, size=GRID_DSZ)
                d.move_to([x0 + c * GRID_COL_DX, y0 - r * GRID_ROW_DY, 0])
                row_dice.append(d)
                dice.add(d)
            self.grid_rows.append(row_dice)
        self.grid_dice = dice

        grid_right = x0 + (cols - 1) * GRID_COL_DX + GRID_DSZ / 2
        grid_bot   = y0 - (rows - 1) * GRID_ROW_DY - GRID_DSZ / 2

        # row sums (3,6,...,18) down the right
        self.row_sums = VGroup()
        for r in range(rows):
            t = crisp_text(str(3 * (r + 1)), font_size=26, color=BLACK,
                           font=FONT, weight="BOLD")
            t.move_to([grid_right + 0.55, y0 - r * GRID_ROW_DY, 0])
            self.row_sums.add(t)

        # col sums (21,21,21) along the bottom
        self.col_sums = VGroup()
        for c in range(cols):
            t = crisp_text("21", font_size=26, color=BLACK, font=FONT, weight="BOLD")
            t.move_to([x0 + c * GRID_COL_DX, grid_bot - 0.5, 0])
            self.col_sums.add(t)

        self.grid_63 = crisp_text("63", font_size=58, color=SCORE_GREEN,
                                  font=FONT, weight="BOLD")
        self.grid_63.move_to([grid_right + 0.55, grid_bot - 0.5, 0])

    def _setup_containers(self):
        self.levels = [3, 6, 9, 12, 15, 18]            # start: 3 of each = full
        walls = VGroup()
        grids = VGroup()
        labels = VGroup()
        self._bg_geom = []
        for i in range(6):
            n = i + 1
            cx = BG_X0 + i * BG_DX
            bottom = TOP_Y - 3 * n * U
            self._bg_geom.append((cx, bottom, n))
            left  = Line([cx - CW / 2, TOP_Y, 0], [cx - CW / 2, bottom, 0],
                         stroke_color=BLACK, stroke_width=3)
            right = Line([cx + CW / 2, TOP_Y, 0], [cx + CW / 2, bottom, 0],
                         stroke_color=BLACK, stroke_width=3)
            base  = Line([cx - CW / 2, bottom, 0], [cx + CW / 2, bottom, 0],
                         stroke_color=BLACK, stroke_width=3)
            walls.add(left, right, base)
            for k in (1, 2):                            # gridlines at 1 and 2 dice
                y = bottom + k * n * U
                grids.add(Line([cx - CW / 2, y, 0], [cx + CW / 2, y, 0],
                               stroke_color=GRID_LINE, stroke_width=1.5))
            labels.add(get_die(n, size=0.34).move_to([cx, BG_LABEL_Y, 0]))
        walls.set_z_index(3)
        grids.set_z_index(3)
        # the common "full = 63" top line
        self.top_line = Line([BG_X0 - CW / 2 - 0.05, TOP_Y, 0],
                             [BG_X0 + 5 * BG_DX + CW / 2 + 0.05, TOP_Y, 0],
                             stroke_color=BLACK, stroke_width=4).set_z_index(3)
        self.bg_walls, self.bg_grids, self.bg_labels = walls, grids, labels
        self.fill_group = self._fill_group(self.levels)

    def _fill_group(self, levels):
        """One VGroup of six [base, over] rect pairs (over may be ~0 tall), so a
        Transform between states morphs smoothly (constant submobject count)."""
        g = VGroup()
        for i, L in enumerate(levels):
            cx, bottom, n = self._bg_geom[i]
            brim = 3 * n
            bh = min(L, brim) * U
            base = Rectangle(width=CW * 0.92, height=max(bh, 1e-4),
                             fill_color=FILL_BLUE, fill_opacity=0.9, stroke_width=0)
            base.move_to([cx, bottom + bh / 2, 0])
            oh = max(L - brim, 0) * U
            over = Rectangle(width=CW * 0.92, height=max(oh, 1e-4),
                             fill_color=FILL_GOLD, fill_opacity=0.95, stroke_width=0)
            over.move_to([cx, TOP_Y + oh / 2, 0])
            g.add(VGroup(base, over))
        g.set_z_index(1)
        return g

    def _set_levels(self, new_levels, run_time):
        target = self._fill_group(new_levels)
        self.play(Transform(self.fill_group, target), run_time=run_time)
        self.levels = list(new_levels)

    def _gold_block(self, height_pts, cx):
        """A free-floating gold surplus block, `height_pts` tall, centered at cx
        just above the top line (its home before it slides/drops)."""
        h = height_pts * U
        return Rectangle(width=CW * 0.92, height=h, fill_color=FILL_GOLD,
                         fill_opacity=0.95, stroke_width=0).set_z_index(2) \
                        .move_to([cx, TOP_Y + h / 2, 0])

    def _setup_table(self):
        self.tcells = {}                                # (count,col) -> Rectangle
        self.ttexts = {}                                # (count,col) -> Text
        cells = VGroup()
        for count in COUNTS_TOP_DOWN:
            y = TB_HEAD_Y - (COUNTS_TOP_DOWN.index(count) + 1) * TB_DY
            for col in range(6):
                x = TB_X0 + col * TB_DX
                cell = Rectangle(width=TB_CW, height=TB_CH, fill_color=NEUTRAL_C,
                                 fill_opacity=1.0, stroke_color=GRID_LINE,
                                 stroke_width=1.5).move_to([x, y, 0])
                self.tcells[(count, col)] = cell
                cells.add(cell)
                t = crisp_text(f"{TABLE[count][col]:.1f}", font_size=22,
                               color=BLACK, font=FONT, weight="BOLD").move_to([x, y, 0])
                self.ttexts[(count, col)] = t

        # column headers = small dice 1..6; row labels = the count
        heads = VGroup()
        for col in range(6):
            heads.add(get_die(col + 1, size=0.36).move_to(
                [TB_X0 + col * TB_DX, TB_HEAD_Y, 0]))
        rlabels = VGroup()
        for count in COUNTS_TOP_DOWN:
            y = TB_HEAD_Y - (COUNTS_TOP_DOWN.index(count) + 1) * TB_DY
            rlabels.add(crisp_text(str(count), font_size=24, color=BLACK,
                                   font=FONT, weight="BOLD").move_to(
                [TB_X0 - TB_DX, y, 0]))
        self.row_head = crisp_text("# scored", font_size=18, color=BLACK,
                                   font=FONT).move_to([TB_X0 - TB_DX, TB_HEAD_Y, 0])

        self.table_static = VGroup(cells, heads, rlabels, self.row_head)
        self.table_card = card_behind(self.table_static, pad=0.32)

        # turn-0 EV above the table
        self.ev_num = crisp_text(f"{BASE_EV:.1f}", font_size=40, color=BLACK,
                                 font=FONT, weight="BOLD").move_to([TB_X0 + 1.5 * TB_DX, EV_Y, 0])
        self.ev_cap = crisp_text("avg top-bonus pts", font_size=22, color=BLACK,
                                 font=FONT).next_to(self.ev_num, LEFT, buff=0.3)

    def _cell_target(self, count, col):
        c = self.tcells[(count, col)]
        return (c.get_center(), c.width, c.height)

    # ══ subscenes ═══════════════════════════════════════════════════════════════
    # a) empty card slides in from the left; highlight the top section
    @subscene
    def top_section(self):
        self._setup_card()
        in_rt = 0.9
        self.card.shift(LEFT * 2.5).set_opacity(0.0)
        self.add(self.card)
        self.play(self.card.animate.shift(RIGHT * 2.5).set_opacity(1.0), run_time=in_rt)
        self.card.highlight_rows(self, list(range(6)), hold=1.2)

    # b) 6 rows of 3 dice -> row sums (3..18) -> col sums (21,21,21) -> merge to 63
    @subscene
    def three_of_each(self):
        self._setup_grid()
        pop, row_rt, col_rt, merge_rt = 0.7, 0.9, 0.7, 0.9
        self.play(LaggedStart(*[FadeIn(d, scale=0.6) for d in self.grid_dice],
                              lag_ratio=0.04), run_time=pop)
        # row sums, flashing each row as its total appears
        for r in range(6):
            self.play(*[FlashFill(d, ACCENT_GOLD, scale_factor=1.15)
                        for d in self.grid_rows[r]],
                      FadeIn(self.row_sums[r], shift=RIGHT * 0.2),
                      run_time=row_rt * 0.5)
        # column sums
        self.play(LaggedStart(*[FadeIn(t, shift=DOWN * 0.2) for t in self.col_sums],
                              lag_ratio=0.15), run_time=col_rt)
        # merge every partial total into a single 63 (bottom right)
        merged = VGroup(self.row_sums.copy(), self.col_sums.copy())
        self.play(ReplacementTransform(merged, self.grid_63),
                  self.row_sums.animate.set_opacity(0.0),
                  self.col_sums.animate.set_opacity(0.0), run_time=merge_rt)

    # c) clear the right; draw the six empty hanging containers
    @subscene
    def empty_containers(self):
        self._setup_containers()
        clear_rt, draw_rt = 0.6, 1.0
        self.play(FadeOut(self.grid_dice), FadeOut(self.grid_63),
                  FadeOut(self.row_sums), FadeOut(self.col_sums), run_time=clear_rt)
        self.play(Create(self.top_line),
                  LaggedStart(*[Create(m) for m in self.bg_walls], lag_ratio=0.03),
                  run_time=draw_rt)
        self.play(FadeIn(self.bg_grids), FadeIn(self.bg_labels), run_time=0.6)

    # d) the fill demo (ROUGHEST beat — states + two slide-and-drop gestures)
    @subscene
    def fill_containers(self):
        fill_rt, step_rt, slide_rt, drop_rt, clear_rt = 0.9, 0.8, 0.7, 0.7, 0.7

        # fill all six to the brim: 3 of each = 63
        self.add(self.fill_group)
        self.play(FadeIn(self.fill_group), run_time=fill_rt)

        # 4 fours & 4 twos overflow the top line
        self._set_levels([3, 8, 9, 16, 15, 18], step_rt)
        # drop to 2 fours & 2 twos (now short of the line)
        self._set_levels([3, 4, 9, 8, 15, 18], step_rt)
        # 3 of everything except 4 fours (overflow 4) and 2 threes (short 3)
        self._set_levels([3, 6, 6, 16, 15, 18], step_rt)

        # slide the surplus 4 from the 4's over into the 3's -> overflow the 3's by 1
        cx4 = self._bg_geom[3][0]
        cx3 = self._bg_geom[2][0]
        cx1 = self._bg_geom[0][0]
        blk = self._gold_block(4, cx4)
        self.add(blk)
        # (the fill_group's 4's overflow is hidden behind blk; drop 4's to full now)
        self._set_levels([3, 6, 6, 12, 15, 18], 0.3)
        self.play(blk.animate.move_to([cx3, TOP_Y + 4 * U / 2, 0]), run_time=slide_rt)
        self.play(FadeOut(blk),
                  Transform(self.fill_group, self._fill_group([3, 6, 10, 12, 15, 18])),
                  run_time=drop_rt)
        self.levels = [3, 6, 10, 12, 15, 18]

        # pull it back out, fill the 3rd 3 legitimately, empty the 1's
        blk2 = self._gold_block(4, cx3)
        self.add(blk2)
        self._set_levels([3, 6, 6, 12, 15, 18], 0.3)     # 3's back to 2 threes
        self.play(blk2.animate.shift(UP * 1.0), run_time=step_rt * 0.6)
        self._set_levels([3, 6, 9, 12, 15, 18], step_rt)  # fill the 3rd 3
        self._set_levels([0, 6, 9, 12, 15, 18], step_rt)  # empty the 1's

        # slide the surplus 4 into the empty 1's -> overflow by 1
        self.play(blk2.animate.move_to([cx1, TOP_Y + 4 * U / 2 + 1.0, 0]),
                  run_time=slide_rt * 0.5)
        self.play(blk2.animate.move_to([cx1, TOP_Y + 4 * U / 2, 0]), run_time=slide_rt * 0.6)
        self.play(FadeOut(blk2),
                  Transform(self.fill_group, self._fill_group([4, 6, 9, 12, 15, 18])),
                  run_time=drop_rt)
        self.levels = [4, 6, 9, 12, 15, 18]

        # clear the right side
        self.play(FadeOut(self.fill_group), FadeOut(self.bg_walls),
                  FadeOut(self.bg_grids), FadeOut(self.bg_labels),
                  FadeOut(self.top_line), run_time=clear_rt)

    # e) empty table + the turn-0 EV (23.8)
    @subscene
    def table_empty(self):
        self._setup_table()
        card_rt, tbl_rt, ev_rt = 0.6, 0.8, 0.6
        self.play(FadeIn(self.table_card), run_time=card_rt)
        self.play(FadeIn(self.table_static), run_time=tbl_rt)
        self.play(FadeIn(self.ev_cap, shift=UP * 0.2),
                  FadeIn(self.ev_num, shift=UP * 0.2), run_time=ev_rt)

    def _reveal_row(self, count, run_time):
        anims = []
        for col in range(6):
            anims.append(self.tcells[(count, col)].animate.set_fill(
                _cell_color(TABLE[count][col]), opacity=1.0))
            self.add(self.ttexts[(count, col)])
            self.ttexts[(count, col)].set_opacity(0.0)
            anims.append(self.ttexts[(count, col)].animate.set_opacity(1.0))
        self.play(*anims, run_time=run_time)

    # f) reveal the count-3 row (barely changes the odds)
    @subscene
    def fill_3(self):
        self._reveal_row(3, 0.8)

    # g) reveal the count-4 row (odds jump, most for larger numbers)
    @subscene
    def fill_4(self):
        self._reveal_row(4, 0.8)

    # h) reveal count-2; highlight 2 ones, then 2 sixes
    @subscene
    def fill_2(self):
        self._reveal_row(2, 0.8)
        highlight(self, [self._cell_target(2, 0)], hold=1.0)   # 2 ones
        highlight(self, [self._cell_target(2, 5)], hold=1.0)   # 2 sixes

    # i) reveal count-1, then count-0; highlight the 0 row in groups
    @subscene
    def fill_1_0(self):
        self._reveal_row(1, 0.8)
        self._reveal_row(0, 0.8)
        highlight(self, [self._cell_target(0, 0), self._cell_target(0, 1)], hold=1.0)  # 0 ones/twos
        highlight(self, [self._cell_target(0, 2)], hold=1.0)                            # 0 threes
        highlight(self, [self._cell_target(0, c) for c in (3, 4, 5)], hold=1.0)         # rest
