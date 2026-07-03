from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.scorecard import get_scorecard
from assets.dice import get_die
from bpkfigures.card import get_card
from bpkfigures.highlight import highlight, overlay_rect


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
# The shared right card: same height as the scorecard, nearly the full remaining
# width (from just right of the scorecard to near the frame edge).
RC     = [2.7, 0.0, 0]
RC_W, RC_H = 8.7, 5.4

# beat b: 6 COLUMNS x 3 identical dice (col c = value c+1), sums add up, merge to 63
GRID_DSZ  = 0.8
GCOL_DX   = 1.05
GROW_DY   = 0.92
GCOL_X0, GROW_Y0 = 0.35, 1.0            # col-0 / row-0 die center
SUM_FS    = 32
COLSUM_Y  = GROW_Y0 - 2 * GROW_DY - 0.72
ROWSUM_X  = GCOL_X0 + 5 * GCOL_DX + 0.9

# beat c/d: the hanging containers
U        = 0.17                         # points -> screen units
TOP_Y    = 1.6                          # the common top the bars hang from
BG_X0    = 0.5
BG_DX    = 1.05
CW       = 0.6                          # container inner width
BG_LABEL_Y = -1.9
FILL_BLUE  = "#9FC5E8"                  # light blue so the dashed value-lines read
FILL_GOLD  = ACCENT_GOLD                # the "extra" that overflows / slides
SUM_POS    = [6.4, 2.3, 0]             # running "sum of container values" corner

# beat e-i: the table
TB_X0, TB_DX = 0.7, 1.0                 # data col 0 center, col spacing
TB_HEAD_Y    = 1.9
TB_DY        = 0.82
TB_CW, TB_CH = 0.92, 0.78
CELL_FS      = 30
EV_POS       = [3.0, 2.5, 0]

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

    Scorecard sits LEFT the whole scene; ONE full-height shared card sits on the
    RIGHT (from beat b on) and every right-side visual fills it: the "3-of-each =
    63" dice grid (b), the hanging open-top containers + fill demo (c, d), then the
    turn-1 EV table (e-i). Follows animated scene 08 (a brings the card IN);
    precedes talking-head THG (so it may end with the table on screen).

      top_section     — beginning-of-game card in from left; highlight top section
      three_of_each   — 6 cols x 3 dice; pips add up to sums, then merge to 63
      empty_containers— clear; draw the six hanging open-top containers
      fill_containers — "3 of each fills it; surplus pours over and slides"
      table_empty     — empty 6x5 EV table + the turn-0 EV (23.8)
      fill_3 / fill_4 / fill_2 / fill_1_0 — reveal rows 3, 4, 2, then 1 & 0
    """

    def setup_scene(self):
        # Scene 08 (animated) leaves the screen empty; a animates the card in.
        pass

    # ══ builders ════════════════════════════════════════════════════════════════
    def _setup_card(self):
        # A scorecard as at the START of a game: all boxes empty, but the (63) bar
        # and top-section summary column present (scores=[None]*14, not None).
        self.card = get_scorecard(center=CARD_L, scores=[None] * 14)

    def _make_right_card(self):
        # ONE owner: beat b builds the shared right card; later beats reference it.
        self.right_card = get_card(RC_W, RC_H, center=RC).set_z_index(-5)

    def _setup_grid(self):
        self._make_right_card()
        self.grid = [[None] * 6 for _ in range(3)]
        flat = VGroup()
        for r in range(3):
            for c in range(6):                          # col c -> value c+1
                d = get_die(c + 1, size=GRID_DSZ)
                d.move_to([GCOL_X0 + c * GCOL_DX, GROW_Y0 - r * GROW_DY, 0])
                self.grid[r][c] = d
                flat.add(d)
        self.grid_dice = flat
        self.grid_cols = [[self.grid[r][c] for r in range(3)] for c in range(6)]
        self.grid_rows = [[self.grid[r][c] for c in range(6)] for r in range(3)]

    def _pips_of(self, dice):
        """Copies of the currently-lit pips of `dice` (for the fly-into-number)."""
        g = VGroup()
        for d in dice:
            for p in d._pips.values():
                if p.get_fill_opacity() > 0.5:
                    g.add(p.copy())
        return g

    def _sum_text(self, s, pos, fs=SUM_FS):
        return crisp_text(str(s), font_size=fs, color=BLACK, font=FONT,
                          weight="BOLD").move_to(pos)

    def _setup_containers(self):
        self.levels = [0, 0, 0, 0, 0, 0]               # start empty; d fills them
        walls, lines, tops, labels = VGroup(), VGroup(), VGroup(), VGroup()
        self._bg_geom = []
        for i in range(6):
            n = i + 1
            cx = BG_X0 + i * BG_DX
            bottom = TOP_Y - 3 * n * U
            self._bg_geom.append((cx, bottom, n))
            walls.add(                                  # open-top U: no line over the mouth
                Line([cx - CW / 2, TOP_Y, 0], [cx - CW / 2, bottom, 0],
                     stroke_color=BLACK, stroke_width=3),
                Line([cx + CW / 2, TOP_Y, 0], [cx + CW / 2, bottom, 0],
                     stroke_color=BLACK, stroke_width=3),
                Line([cx - CW / 2, bottom, 0], [cx + CW / 2, bottom, 0],
                     stroke_color=BLACK, stroke_width=3),
            )
            for k in (1, 2):                            # value-lines at 1 and 2 dice
                y = bottom + k * n * U
                lines.add(DashedLine([cx - CW / 2, y, 0], [cx + CW / 2, y, 0],
                                     dash_length=0.09, stroke_color=BLACK,
                                     stroke_width=2))
            labels.add(get_die(n, size=0.4).move_to([cx, BG_LABEL_Y, 0]))
        for i in range(5):                              # top segments BETWEEN containers
            x1 = self._bg_geom[i][0] + CW / 2
            x2 = self._bg_geom[i + 1][0] - CW / 2
            tops.add(Line([x1, TOP_Y, 0], [x2, TOP_Y, 0],
                          stroke_color=BLACK, stroke_width=3))
        for grp in (walls, lines, tops):
            grp.set_z_index(3)
        self.bg_walls, self.bg_lines, self.bg_top, self.bg_labels = walls, lines, tops, labels
        self.cfills = {i: self._cfill(i, 0) for i in range(6)}
        self.bg_sum = self._sum_text(0, SUM_POS, fs=46)

    def _cfill(self, i, level):
        """One container's fill: blue water (bottom→min(level,brim)) + gold overflow
        (brim→level, above the top)."""
        cx, bottom, n = self._bg_geom[i]
        brim = 3 * n
        bh = min(level, brim) * U
        base = Rectangle(width=CW * 0.9, height=max(bh, 1e-4), fill_color=FILL_BLUE,
                         fill_opacity=0.95, stroke_width=0).move_to([cx, bottom + bh / 2, 0])
        oh = max(level - brim, 0) * U
        over = Rectangle(width=CW * 0.9, height=max(oh, 1e-4), fill_color=FILL_GOLD,
                         fill_opacity=0.95, stroke_width=0).move_to([cx, TOP_Y + oh / 2, 0])
        return VGroup(base, over).set_z_index(1)

    def _apply(self, new_levels, mode, run_time, sum_val=None):
        """Move the container fills to `new_levels`. mode='grow' animates the water
        rising/falling (a real fill); mode='fade' cross-fades (a reconfiguration —
        scoring different dice). Optionally retitle the corner sum."""
        anims, swaps = [], {}
        for i in range(6):
            if new_levels[i] == self.levels[i]:
                continue
            ng = self._cfill(i, new_levels[i])
            if mode == "grow":
                anims.append(Transform(self.cfills[i], ng))
            else:
                anims.append(FadeOut(self.cfills[i]))
                anims.append(FadeIn(ng))
                swaps[i] = ng
        if sum_val is not None:
            anims.append(Transform(self.bg_sum, self._sum_text(sum_val, SUM_POS, fs=46)))
        if anims:
            self.play(*anims, run_time=run_time)
        for i, ng in swaps.items():
            self.remove(self.cfills[i])
            self.cfills[i] = ng
        self.levels = list(new_levels)

    def _grow(self, levels, run_time, sum_val=None):
        self._apply(levels, "grow", run_time, sum_val)

    def _fade(self, levels, run_time, sum_val=None):
        self._apply(levels, "fade", run_time, sum_val)

    def _block(self, cx, y):
        return Rectangle(width=CW * 0.9, height=4 * U, fill_color=FILL_GOLD,
                         fill_opacity=0.95, stroke_width=0).set_z_index(2) \
                        .move_to([cx, y, 0])

    def _setup_table(self):
        self.tcells, self.ttexts = {}, {}
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
                self.ttexts[(count, col)] = crisp_text(
                    f"{TABLE[count][col]:.1f}", font_size=CELL_FS, color=BLACK,
                    font=FONT, weight="BOLD").move_to([x, y, 0])

        heads = VGroup(*[get_die(col + 1, size=0.5).move_to(
            [TB_X0 + col * TB_DX, TB_HEAD_Y, 0]) for col in range(6)])
        rlabels = VGroup()
        for count in COUNTS_TOP_DOWN:
            y = TB_HEAD_Y - (COUNTS_TOP_DOWN.index(count) + 1) * TB_DY
            rlabels.add(crisp_text(str(count), font_size=34, color=BLACK,
                                   font=FONT, weight="BOLD").move_to(
                [TB_X0 - TB_DX, y, 0]))
        self.row_head = crisp_text("# scored", font_size=22, color=BLACK,
                                   font=FONT).move_to([TB_X0 - TB_DX, TB_HEAD_Y, 0])
        self.table_static = VGroup(cells, heads, rlabels, self.row_head)

        self.ev_num = crisp_text(f"{BASE_EV:.1f}", font_size=54, color=BLACK,
                                 font=FONT, weight="BOLD").move_to(EV_POS)
        self.ev_cap = crisp_text("avg top-bonus pts", font_size=26, color=BLACK,
                                 font=FONT).next_to(self.ev_num, LEFT, buff=0.35)

    def _cell_target(self, count, col):
        c = self.tcells[(count, col)]
        return (c.get_center(), c.width, c.height)

    def _highlight_cells(self, cells, *, hold=1.0, fade=0.25):
        """Our established highlight() gold-hold, PLUS a thick black cell border and
        enlarged cell text on the spotlighted cells; all restored after the hold."""
        rects   = [overlay_rect(self.tcells[c], color=ACCENT_GOLD, opacity=0.5)
                   for c in cells]
        borders = [self.tcells[c] for c in cells]
        texts   = [self.ttexts[c] for c in cells]
        for m in borders + texts:
            m.save_state()
        self.play(*[FadeIn(r) for r in rects],
                  *[b.animate.set_stroke(BLACK, width=6) for b in borders],
                  *[t.animate.scale(1.4) for t in texts], run_time=fade)
        self.wait(hold)
        self.play(*[FadeOut(r) for r in rects],
                  *[Restore(b) for b in borders],
                  *[Restore(t) for t in texts], run_time=fade)
        self.remove(*rects)

    # ══ subscenes ═══════════════════════════════════════════════════════════════
    # a) beginning-of-game card slides in; highlight the top section (all 3 columns)
    @subscene
    def top_section(self):
        self._setup_card()
        in_rt = 0.9
        self.card.shift(LEFT * 2.5).set_opacity(0.0)
        self.add(self.card)
        self.play(self.card.animate.shift(RIGHT * 2.5).set_opacity(1.0), run_time=in_rt)
        # a region spanning rows 0-5 across ALL three columns (incl. the (63) column)
        hdr = self.card.header_rect
        left, right = hdr.get_left()[0], hdr.get_right()[0]
        ytop = self.card.value_cells[0].get_top()[1]
        ybot = self.card.value_cells[5].get_bottom()[1]
        region = ([(left + right) / 2, (ytop + ybot) / 2, 0], right - left, ytop - ybot)
        highlight(self, [region], hold=1.2)

    # b) 6 cols of 3 dice; pips add up (all col & row sums at once) -> merge to 63
    @subscene
    def three_of_each(self):
        self._setup_grid()
        card_rt, pop, add_rt, hold, merge_rt = 0.6, 0.7, 1.2, 0.5, 1.0
        self.play(FadeIn(self.right_card), run_time=card_rt)
        self.play(LaggedStart(*[FadeIn(d, scale=0.6) for d in self.grid_dice],
                              lag_ratio=0.04), run_time=pop)

        # every column sum (3v, under each column) AND every row sum (21, right of
        # each row) form at the SAME time, each from copies of the relevant pips.
        self.sum_texts = VGroup()
        anims, copies = [], VGroup()
        for c in range(6):
            num = self._sum_text(3 * (c + 1),
                                 [self.grid_cols[c][0].get_center()[0], COLSUM_Y, 0])
            pc = self._pips_of(self.grid_cols[c])
            copies.add(pc); self.sum_texts.add(num)
            anims.append(ReplacementTransform(pc, num))
        for r in range(3):
            num = self._sum_text(21, [ROWSUM_X, self.grid_rows[r][0].get_center()[1], 0])
            pc = self._pips_of(self.grid_rows[r])
            copies.add(pc); self.sum_texts.add(num)
            anims.append(ReplacementTransform(pc, num))
        self.add(copies)
        self.play(*anims, run_time=add_rt)
        self.wait(hold)

        # merge every partial total into a single BLACK 63 (bottom right)
        self.big63 = self._sum_text(63, [ROWSUM_X, COLSUM_Y, 0], fs=70)
        self.play(ReplacementTransform(self.sum_texts, self.big63), run_time=merge_rt)

    # c) clear the right content (card stays); draw the six hanging containers, the
    #    top connectors, and the running container-total (starts at 0)
    @subscene
    def empty_containers(self):
        self._setup_containers()
        clear_rt, draw_rt, line_rt = 0.6, 1.0, 0.6
        self.play(FadeOut(self.grid_dice), FadeOut(self.big63), run_time=clear_rt)
        self.add(*self.cfills.values())                 # invisible at level 0
        self.play(LaggedStart(*[Create(m) for m in self.bg_walls], lag_ratio=0.04),
                  Create(self.bg_top), run_time=draw_rt)
        self.play(FadeIn(self.bg_lines), FadeIn(self.bg_labels),
                  FadeIn(self.bg_sum), run_time=line_rt)

    # d) the fill demo: 3-step fill, fade-reconfigures, then fall-in-from-the-top slides
    @subscene
    def fill_containers(self):
        fill_rt, fade_rt, lift_rt, across_rt, drop_rt, clear_rt = \
            0.7, 0.7, 0.6, 0.7, 0.7, 0.7
        cx1, cx3, cx4 = self._bg_geom[0][0], self._bg_geom[2][0], self._bg_geom[3][0]
        hold_y, drop_y = TOP_Y + 2 * U + 0.7, TOP_Y - U

        # fill one slot at a time across all six: 1 of each, 2 of each, 3 of each
        self._grow([1, 2, 3, 4, 5, 6],       fill_rt, sum_val=21)
        self._grow([2, 4, 6, 8, 10, 12],     fill_rt, sum_val=42)
        self._grow([3, 6, 9, 12, 15, 18],    fill_rt, sum_val=63)

        # reconfigure via FADE (scoring different dice, not filling/emptying)
        self._fade([3, 8, 9, 16, 15, 18],    fade_rt, sum_val=69)   # 4 fours & 4 twos
        self._fade([3, 4, 9,  8, 15, 18],    fade_rt, sum_val=51)   # 2 fours & 2 twos
        self._fade([3, 6, 6, 16, 15, 18],    fade_rt, sum_val=64)   # 4 fours, 2 threes

        # slide the surplus 4 from the fours into the threes: lift out, across, fall in
        blk = self._block(cx4, TOP_Y + 2 * U)
        self.add(blk)
        self._grow([3, 6, 6, 12, 15, 18], 0.25)          # fours to full (hidden by blk)
        self.play(blk.animate.move_to([cx4, hold_y, 0]), run_time=lift_rt)
        self.play(blk.animate.move_to([cx3, hold_y, 0]), run_time=across_rt)
        self.play(blk.animate.move_to([cx3, drop_y, 0]), run_time=drop_rt)  # rests on the water

        # pull it back out, add the 3rd 3 for real, empty the ones, slide into the ones
        self.play(blk.animate.move_to([cx3, hold_y, 0]), run_time=lift_rt)
        self._grow([3, 6, 9, 12, 15, 18], fade_rt)       # 3rd three (a real die)
        self._fade([0, 6, 9, 12, 15, 18], fade_rt)       # zero the ones
        self.play(blk.animate.move_to([cx1, hold_y, 0]), run_time=across_rt)
        self.play(blk.animate.move_to([cx1, drop_y, 0]), run_time=drop_rt)  # falls to the empty ones

        self.play(FadeOut(blk), *[FadeOut(g) for g in self.cfills.values()],
                  FadeOut(self.bg_walls), FadeOut(self.bg_lines), FadeOut(self.bg_top),
                  FadeOut(self.bg_labels), FadeOut(self.bg_sum), run_time=clear_rt)

    # e) empty table + the turn-0 EV (23.8)
    @subscene
    def table_empty(self):
        self._setup_table()
        tbl_rt, ev_rt = 0.8, 0.6
        self.play(FadeIn(self.table_static), run_time=tbl_rt)
        self.play(FadeIn(self.ev_cap, shift=UP * 0.2),
                  FadeIn(self.ev_num, shift=UP * 0.2), run_time=ev_rt)

    def _reveal_row(self, count, run_time, lag=0.14):
        anims = []
        for col in range(6):
            cell, t = self.tcells[(count, col)], self.ttexts[(count, col)]
            self.add(t); t.set_opacity(0.0)
            anims.append(AnimationGroup(
                cell.animate.set_fill(_cell_color(TABLE[count][col]), opacity=1.0),
                t.animate.set_opacity(1.0)))
        self.play(LaggedStart(*anims, lag_ratio=lag), run_time=run_time)  # cascade L->R

    # f) reveal the count-3 row (barely changes the odds)
    @subscene
    def fill_3(self):
        self._reveal_row(3, 1.0)

    # g) reveal the count-4 row (odds jump, most for larger numbers)
    @subscene
    def fill_4(self):
        self._reveal_row(4, 1.0)

    # h) reveal count-2; highlight 2 ones, then 2 sixes
    @subscene
    def fill_2(self):
        self._reveal_row(2, 1.0)
        self._highlight_cells([(2, 0)], hold=1.0)     # 2 ones
        self._highlight_cells([(2, 5)], hold=1.0)     # 2 sixes

    # i) reveal count-1, then count-0; highlight the 0 row in groups
    @subscene
    def fill_1_0(self):
        self._reveal_row(1, 1.0)
        self._reveal_row(0, 1.0)
        self._highlight_cells([(0, 0), (0, 1)], hold=1.0)          # 0 ones/twos
        self._highlight_cells([(0, 2)], hold=1.0)                  # 0 threes
        self._highlight_cells([(0, 3), (0, 4), (0, 5)], hold=1.0)  # rest
