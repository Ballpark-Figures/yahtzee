from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from manim import *
from config import *
from assets.dice import (
    FlashFill, reorder_dice, ascend_and_flash, jump_and_spin, spin_into,
)
import numpy as np

SCORE_ROWS = [
    "Ones",
    "Twos",
    "Threes",
    "Fours",
    "Fives",
    "Sixes",
    "3 of a Kind",
    "4 of a Kind",
    "Full House",
    "Sm Straight",
    "Lg Straight",
    "Yahtzee",
    "Chance",
]

BOTTOM_START = 6   # first row index of bottom section
TOP_ROWS     = 6   # rows spanned by top summary column
BOTTOM_ROWS  = 7   # rows spanned by bottom summary column
YAHTZEE_IDX  = 11  # index of Yahtzee row in SCORE_ROWS

# scores[0..5]  → Ones–Sixes
# scores[6..12] → 3 of a Kind–Chance
# scores[13]    → Yahtzee Bonus
def _compute(scores):
    top           = scores[0:6]
    bottom_scores = scores[6:13]   # 3ofK–Chance
    yahtzee_bonus = scores[13]     # scores[13]

    top_complete    = all(s is not None for s in top)
    bottom_complete = all(s is not None for s in bottom_scores)
    any_top         = any(s is not None for s in top)
    any_bottom      = any(s is not None for s in bottom_scores)

    top_sum          = sum(s for s in top           if s is not None)
    bottom_sum       = sum(s for s in bottom_scores if s is not None)   # excludes yahtzee bonus
    top_bonus_earned = top_sum >= 63
    top_total        = top_sum + (35 if top_bonus_earned else 0)

    rows = []
    for s in top:
        rows.append((s, BLACK, 1.0))
    for s in bottom_scores:
        rows.append((s, BLACK, 1.0))

    return dict(
        rows=rows,
        top_sum=top_sum, top_complete=top_complete,
        top_bonus_earned=top_bonus_earned, top_total=top_total,
        bottom_sum=bottom_sum, bottom_complete=bottom_complete,
        yahtzee_bonus=yahtzee_bonus,
        any_top=any_top, any_bottom=any_bottom,
    )


class Scorecard(VGroup):
    """A Yahtzee scorecard that can both render statically and animate scoring.

    Build it with a list of `scores` (use None for empty boxes), add it to a
    scene, then drive box-scoring animations with `animate_top_score`.
    Handles to the animatable parts (progress bar, bar number, the "(63)"
    label, the Total) are kept as attributes and mutated in place.
    """

    def __init__(
        self,
        scores=None,
        center=CENTER_SC,
        cell_height=0.47,
        label_width=2.8,
        value_width=1.1,
        summary_width=1.2,
        font_size=SCORECARD_FONT_SIZE,
        stroke_color=BLACK,
        stroke_width=1.5,
        grid_color=GRID_LINE,
        grid_width=1.0,
        text_pad=0.12,
        section_gap=0.4,
        bottom_gap=1.0,
        show_summary=True,
    ):
        super().__init__()
        # show_summary=False removes the 3rd-column CONTENTS only (the (63) bar,
        # running totals, bottom total, grand total) — the column outline, the
        # box scores, and the Total footer bar all stay.
        self.show_summary = show_summary
        self.cell_height = cell_height
        self.font_size   = font_size
        self.text_pad    = text_pad

        # animatable handles
        self.value_cells = {}     # row -> value Rectangle
        self.value_texts = {}     # row -> score Text
        self.bar_border       = None
        self.bar_fill         = None
        self.bar_number       = None
        self.cap_label        = None   # "(63)"
        self.bonus_label      = None   # "+35"
        self.total_text       = None
        self.bottom_total_text = None
        self.yahtzee_bonus_text = None
        self._top_sum         = 0
        self._bottom_sum      = 0
        self._yahtzee_bonus   = 0
        self._yahtzee_is_50   = False   # Yahtzee box holds a real 50 (bonus-eligible)

        self.cells       = VGroup()
        self.labels      = VGroup()
        self.score_texts = VGroup()

        self._build(scores, label_width, value_width, summary_width,
                    stroke_color, stroke_width, grid_color, grid_width,
                    section_gap, bottom_gap)

        self.add(self.cells, self.labels, self.score_texts)
        self.move_to(center)

    # ── Static build ─────────────────────────────────────────────────────────
    def _build(self, scores, label_width, value_width, summary_width,
               stroke_color, stroke_width, grid_color, grid_width,
               section_gap, bottom_gap):
        cell_height = self.cell_height
        font_size   = self.font_size
        text_pad    = self.text_pad
        cells, labels, score_texts = self.cells, self.labels, self.score_texts

        n = len(SCORE_ROWS)
        total_height = n * cell_height + section_gap + bottom_gap

        full_width = label_width + value_width + summary_width
        left_edge  = -full_width / 2
        label_x    = left_edge + label_width / 2
        value_x    = left_edge + label_width + value_width / 2
        summary_x  = left_edge + label_width + value_width + summary_width / 2

        bottom_edge = total_height / 2 - (BOTTOM_START + BOTTOM_ROWS) * cell_height - section_gap
        total_y     = bottom_edge - cell_height / 2

        # ── Card surface ─────────────────────────────────────────────────────
        grid_top    = total_height / 2
        header_h    = cell_height * 1.2
        header_cy   = grid_top + header_h / 2

        panel_pad   = 0.18
        content_top = grid_top + header_h
        content_bot = total_y - cell_height * 0.7
        panel = RoundedRectangle(
            width=full_width + 2 * panel_pad,
            height=(content_top - content_bot) + 2 * panel_pad,
            corner_radius=0.22,
            fill_color=CARD_FILL, fill_opacity=1.0,
            stroke_color=stroke_color, stroke_width=stroke_width * 2,
        ).move_to(np.array([0, (content_top + content_bot) / 2, 0]))
        cells.add(panel)

        header = Rectangle(
            width=full_width, height=header_h,
            fill_color=ACCENT_FILL, fill_opacity=1.0,
            stroke_color=grid_color, stroke_width=grid_width,
        ).move_to(np.array([0, header_cy, 0]))
        cells.add(header)
        title = crisp_text("YAHTZEE", font_size=font_size * 1.15, color=WHITE, font=FONT, weight="BOLD")
        title.move_to(np.array([0, header_cy, 0]))
        score_texts.add(title)

        c = _compute(scores) if scores is not None else None

        # ── Score rows ───────────────────────────────────────────────────────
        for i, label in enumerate(SCORE_ROWS):
            gap_offset = section_gap if i >= BOTTOM_START else 0
            y = total_height / 2 - (i + 0.5) * cell_height - gap_offset

            if i % 2 == 1:
                cells.add(Rectangle(
                    width=label_width + value_width, height=cell_height,
                    fill_color=STRIPE_FILL, fill_opacity=1.0, stroke_width=0,
                ).move_to(np.array([left_edge + (label_width + value_width) / 2, y, 0])))

            label_cell = Rectangle(
                width=label_width, height=cell_height,
                fill_opacity=0, stroke_color=grid_color, stroke_width=grid_width,
            ).move_to(np.array([label_x, y, 0]))

            value_cell = Rectangle(
                width=value_width, height=cell_height,
                fill_opacity=0, stroke_color=grid_color, stroke_width=grid_width,
            ).move_to(np.array([value_x, y, 0]))
            self.value_cells[i] = value_cell

            text = crisp_text(label, font_size=font_size, color=stroke_color, font=FONT)
            text.align_to(label_cell, LEFT)
            text.shift(RIGHT * text_pad)
            text.set_y(y)

            cells.add(label_cell, value_cell)
            labels.add(text)

            if c is not None:
                val, color, opacity = c["rows"][i]
                if val is not None:
                    sv = crisp_text(str(val), font_size=font_size, color=color, font=FONT)
                    sv.set_fill(color, opacity=opacity)
                    sv.move_to(np.array([value_x, y, 0]))
                    score_texts.add(sv)
                    self.value_texts[i] = sv

        # ── Top summary column ───────────────────────────────────────────────
        top_h          = TOP_ROWS * cell_height
        top_summary_cy = total_height / 2 - top_h / 2

        cells.add(Rectangle(
            width=summary_width, height=top_h,
            fill_opacity=0, stroke_color=grid_color, stroke_width=grid_width,
        ).move_to(np.array([summary_x, top_summary_cy, 0])))

        if c is not None and self.show_summary:
            self._top_sum       = c["top_sum"]
            self._bottom_sum    = c["bottom_sum"]
            self._yahtzee_bonus = c["yahtzee_bonus"] or 0
            top_opacity = 1.0 if c["top_complete"] else 0.5

            bar_top_y = total_height / 2 - 2 * cell_height
            bar_bot_y = total_height / 2 - 5 * cell_height
            bar_h     = bar_top_y - bar_bot_y          # 3 * cell_height
            bar_w     = summary_width * 0.6
            bar_cy    = (bar_top_y + bar_bot_y) / 2

            frac       = c["top_sum"] / 63
            fill_h     = bar_h * frac
            fill_top_y = bar_bot_y + fill_h

            if c["top_sum"] >= 63:
                fill_color = SCORE_GREEN
            elif c["top_complete"]:
                fill_color = SCORE_RED
            else:
                fill_color = ACCENT_FILL

            # bar fill (always present so it can animate from empty)
            self.bar_fill = Rectangle(
                width=bar_w, height=max(fill_h, 1e-4),
                fill_color=fill_color, fill_opacity=1.0, stroke_width=0,
            ).move_to(np.array([summary_x, bar_bot_y + fill_h / 2, 0]))
            cells.add(self.bar_fill)

            # thick border around the full height-63 bar
            self.bar_border = Rectangle(
                width=bar_w, height=bar_h,
                fill_opacity=0, stroke_color=stroke_color, stroke_width=stroke_width * 3,
            ).move_to(np.array([summary_x, bar_cy, 0]))
            cells.add(self.bar_border)

            # "(63)" target label
            hit_63     = c["top_sum"] >= 63
            cap_color  = WHITE if hit_63 else BLACK
            cap_offset = cell_height * 0.35
            cap_y      = bar_top_y - cap_offset if hit_63 else bar_top_y + cap_offset
            self.cap_label = crisp_text("(63)", font_size=font_size * 0.55, color=cap_color, font=FONT, weight="BOLD")
            self.cap_label.set_fill(cap_color, opacity=top_opacity)
            self.cap_label.move_to(np.array([summary_x, cap_y, 0]))
            score_texts.add(self.cap_label)

            # running total number
            below_21   = c["top_sum"] <= 21
            num_color  = BLACK if below_21 else WHITE
            num_offset = cell_height * 0.4
            fives_y    = total_height / 2 - 4.5 * cell_height
            num_y      = fill_top_y + num_offset if below_21 else fives_y
            self.bar_number = crisp_text(str(c["top_sum"]), font_size=font_size, color=num_color, font=FONT, weight="BOLD")
            self.bar_number.set_fill(num_color, opacity=top_opacity)
            self.bar_number.move_to(np.array([summary_x, num_y, 0]))
            score_texts.add(self.bar_number)

            if c["top_bonus_earned"]:
                sixes_y = total_height / 2 - 5.5 * cell_height
                self.bonus_label = crisp_text("+35", font_size=font_size, color=SCORE_GREEN, font=FONT, weight="BOLD")
                self.bonus_label.move_to(np.array([summary_x, sixes_y, 0]))
                score_texts.add(self.bonus_label)

        # ── Bottom summary column ────────────────────────────────────────────
        bottom_h          = BOTTOM_ROWS * cell_height
        bottom_summary_cy = total_height / 2 - BOTTOM_START * cell_height - section_gap - bottom_h / 2

        cells.add(Rectangle(
            width=summary_width, height=bottom_h,
            fill_opacity=0, stroke_color=grid_color, stroke_width=grid_width,
        ).move_to(np.array([summary_x, bottom_summary_cy, 0])))

        # ── Total footer (always shown; the number is omitted when scores=None)
        footer = Rectangle(
            width=full_width, height=cell_height * 1.18,
            fill_color=ACCENT_FILL, fill_opacity=1.0,
            stroke_color=grid_color, stroke_width=grid_width,
        ).move_to(np.array([0, total_y, 0]))
        cells.add(footer)

        tl = crisp_text("Total", font_size=font_size, color=WHITE, font=FONT, weight="BOLD")
        tl.align_to(footer, LEFT)
        tl.shift(RIGHT * text_pad * 1.5)
        tl.set_y(total_y)
        score_texts.add(tl)

        if c is not None and self.show_summary:
            bottom_opacity = 1.0 if c["bottom_complete"] else 0.5

            self.bottom_total_text = crisp_text(str(c["bottom_sum"]), font_size=font_size, color=stroke_color, font=FONT, weight="BOLD")
            self.bottom_total_text.set_fill(stroke_color, opacity=bottom_opacity)
            self.bottom_total_text.move_to(np.array([summary_x, bottom_summary_cy, 0]))
            score_texts.add(self.bottom_total_text)

            if c["yahtzee_bonus"] is not None and c["yahtzee_bonus"] > 0:
                y_yahtzee = total_height / 2 - (YAHTZEE_IDX + 0.5) * cell_height - section_gap
                self.yahtzee_bonus_text = crisp_text(f"+{c['yahtzee_bonus']}", font_size=font_size, color=SCORE_GREEN, font=FONT, weight="BOLD")
                self.yahtzee_bonus_text.move_to(np.array([summary_x, y_yahtzee, 0]))
                score_texts.add(self.yahtzee_bonus_text)

            # the grand total number (omitted entirely when scores=None)
            grand_total    = c["top_total"] + c["bottom_sum"] + (c["yahtzee_bonus"] or 0)
            grand_complete = c["top_complete"] and c["bottom_complete"]

            self.total_text = crisp_text(str(grand_total), font_size=font_size, color=WHITE, font=FONT, weight="BOLD")
            self.total_text.set_fill(WHITE, opacity=1.0 if grand_complete else 0.5)
            self.total_text.move_to(np.array([summary_x, total_y, 0]))
            score_texts.add(self.total_text)

    # ── Animation ────────────────────────────────────────────────────────────
    def animate_top_score(self, scene, row, dice, *, run_time=1.1):
        """Score top-section `row` (0=Ones..5=Sixes) from the dice that match
        its face: flash them, fly copies of their pips into the value box as
        the number, then raise the bar and totals (flashing green at 63)."""
        face     = row + 1
        matching = [d for d in dice if getattr(d, "value", None) == face]
        count    = len(matching)
        add      = face * count
        old      = self._top_sum
        new      = old + add

        # 1. flash the matching dice
        if matching:
            scene.play(*[FlashFill(d, YELLOW, scale_factor=1.18) for d in matching],
                       run_time=0.6)

        # 2. copies of the pips fly into the value box and become the number
        cell   = self.value_cells[row]
        number = crisp_text(str(add), font_size=self.font_size, color=BLACK, font=FONT)
        number.move_to(cell.get_center())

        pip_copies = VGroup()
        for d in matching:
            for p in d._pips.values():
                if p.get_fill_opacity() > 0.5:
                    pip_copies.add(p.copy())

        if len(pip_copies) > 0:
            scene.add(pip_copies)
            scene.play(ReplacementTransform(pip_copies, number), run_time=1.0)
        else:
            scene.play(FadeIn(number))
        self.value_texts[row] = number

        # 3. raise the bar + count the totals (flashes green when crossing 63)
        self._animate_top_total(scene, old, new, run_time)
        self._top_sum = new

    def animate_bottom_score(self, scene, row, dice, *, flash=None, flash_color=YELLOW,
                             pip_dice=None, score=None, run_time=1.1):
        """Score a bottom-section `row` (6=3 of a Kind .. 12=Chance). Optionally
        flash a subset of dice first, then fly copies of `pip_dice`'s pips into
        the box as the number, and tick the bottom-section total + grand total.
        Defaults: no flash, all dice's pips, score = sum of all dice."""
        pip_dice = list(dice) if pip_dice is None else pip_dice
        if score is None:
            score = sum(d.value for d in pip_dice)

        # 1. optional flash
        if flash:
            scene.play(*[FlashFill(d, flash_color, scale_factor=1.18) for d in flash],
                       run_time=0.6)

        # 2. pips fly into the box and become the number
        cell   = self.value_cells[row]
        number = crisp_text(str(score), font_size=self.font_size, color=BLACK, font=FONT)
        number.move_to(cell.get_center())

        pip_copies = VGroup()
        for d in pip_dice:
            for p in d._pips.values():
                if p.get_fill_opacity() > 0.5:
                    pip_copies.add(p.copy())

        if len(pip_copies) > 0:
            scene.add(pip_copies)
            scene.play(ReplacementTransform(pip_copies, number), run_time=1.0)
        else:
            scene.play(FadeIn(number))
        self.value_texts[row] = number

        # 3. tick the bottom total + grand total
        old_b, new_b = self._bottom_sum, self._bottom_sum + score
        self._animate_bottom_total(scene, old_b, new_b, run_time)
        self._bottom_sum = new_b

    def animate_fixed_score(self, scene, row, score, *, flash_color=YELLOW, run_time=1.1):
        """Score a fixed-value bottom box (Full House, straights, Yahtzee): the
        box flashes as the number grows in, then the totals tick up. No pips."""
        cell   = self.value_cells[row]
        number = crisp_text(str(score), font_size=self.font_size, color=BLACK, font=FONT)
        number.move_to(cell.get_center())

        hl = cell.copy()
        hl.set_fill(flash_color, opacity=0.7)
        hl.set_stroke(width=0)
        scene.add(hl)                       # behind the number, which play() adds after
        scene.play(FadeIn(hl, rate_func=there_and_back), GrowFromCenter(number), run_time=0.8)
        scene.remove(hl)
        self.value_texts[row] = number

        old_b, new_b = self._bottom_sum, self._bottom_sum + score
        self._animate_bottom_total(scene, old_b, new_b, run_time)
        self._bottom_sum = new_b

    def animate_zero_score(self, scene, row, dice, *, run_time=1.0):
        """Score a 0 in `row`: bold red X's stamp over the dice all at once
        (battleship-style), merge into a single X in the value box, then become
        a 0. Totals are unchanged (it adds nothing)."""
        xs = VGroup(*[Cross(d, stroke_color=RED, stroke_width=8) for d in dice])
        scene.play(*[GrowFromCenter(x) for x in xs], run_time=0.4)

        cell  = self.value_cells[row]
        box_x = Cross(dice[0], stroke_color=RED, stroke_width=8)
        box_x.scale_to_fit_height(cell.height * 0.75).move_to(cell.get_center())
        scene.play(ReplacementTransform(xs, box_x), run_time=0.7)

        zero = crisp_text("0", font_size=self.font_size, color=BLACK, font=FONT)
        zero.move_to(cell.get_center())
        scene.play(ReplacementTransform(box_x, zero), run_time=0.5)
        self.value_texts[row] = zero

    def fly_to_box(self, scene, dice, colors, row, score, *, run_time=1.0):
        """For color categories: tint copies of `dice` with `colors` (None = leave
        as-is) and fly them into the value box, morphing into the score; then
        tick the bottom total + grand total."""
        cell   = self.value_cells[row]
        number = crisp_text(str(score), font_size=self.font_size, color=BLACK, font=FONT)
        number.move_to(cell.get_center())

        group = VGroup()
        for d, c in zip(dice, colors):
            cp = d.copy()
            if c is not None:
                cp.body.set_fill(ManimColor(c), opacity=1.0)
            group.add(cp)

        scene.add(group)
        scene.play(ReplacementTransform(group, number), run_time=run_time)
        self.value_texts[row] = number

        old_b, new_b = self._bottom_sum, self._bottom_sum + score
        self._animate_bottom_total(scene, old_b, new_b, run_time)
        self._bottom_sum = new_b

    def yahtzee_box_point(self):
        return self.value_cells[YAHTZEE_IDX].get_center()

    def yahtzee_bonus_point(self):
        return np.array([self.bar_border.get_center()[0],
                         self.value_cells[YAHTZEE_IDX].get_center()[1], 0])

    def animate_yahtzee_bonus(self, scene, *, run_time=1.1):
        """Add a +100 Yahtzee bonus: flash the running +N in the Yahtzee row and
        tick the grand total up by 100."""
        old_g = self._top_total() + self._bottom_sum + self._yahtzee_bonus
        self._yahtzee_bonus += 100

        bar_cx = self.bar_border.get_center()[0]
        y      = self.value_cells[YAHTZEE_IDX].get_center()[1]
        label  = crisp_text(f"+{self._yahtzee_bonus}", font_size=self.font_size, color=SCORE_GREEN, font=FONT, weight="BOLD")
        label.move_to(np.array([bar_cx, y, 0]))

        if self.yahtzee_bonus_text is None:
            self.yahtzee_bonus_text = label
            self.score_texts.add(label)
            scene.play(GrowFromCenter(label),
                       Flash(label.get_center(), color=SCORE_GREEN, flash_radius=0.5),
                       run_time=0.8)
        else:
            scene.play(Transform(self.yahtzee_bonus_text, label),
                       Flash(self.yahtzee_bonus_text.get_center(), color=SCORE_GREEN, flash_radius=0.5),
                       run_time=0.8)

        self._tick_total(scene, old_g, old_g + 100, run_time)

    # ── Category scoring: detect the result, then play the right animation ─────
    @staticmethod
    def _counts(dice):
        counts = {}
        for d in dice:
            counts[d.value] = counts.get(d.value, 0) + 1
        return counts

    def upper(self, scene, dice, face):
        """Ones..Sixes (face 1..6): sum of the matching dice, or 0 (X) if none."""
        row = face - 1
        if any(d.value == face for d in dice):
            self.animate_top_score(scene, row, dice)
        else:
            self.animate_zero_score(scene, row, dice)

    def three_of_a_kind(self, scene, dice):
        counts = self._counts(dice)
        kind = max(counts, key=counts.get)
        if counts[kind] >= 3:
            flash = [d for d in dice if d.value == kind]
            self.animate_bottom_score(scene, 6, dice, flash=flash, flash_color=ACCENT_FILL)
        else:
            self.animate_zero_score(scene, 6, dice)

    def four_of_a_kind(self, scene, dice):
        counts = self._counts(dice)
        kind = max(counts, key=counts.get)
        if counts[kind] >= 4:
            flash = [d for d in dice if d.value == kind]
            self.animate_bottom_score(scene, 7, dice, flash=flash, flash_color=SCORE_GREEN)
        else:
            self.animate_zero_score(scene, 7, dice)

    def full_house(self, scene, dice):
        counts = self._counts(dice)
        if sorted(counts.values()) == [2, 3]:
            triple_val = next(v for v, c in counts.items() if c == 3)
            pair_val   = next(v for v, c in counts.items() if c == 2)
            triple = [d for d in dice if d.value == triple_val]
            pair   = [d for d in dice if d.value == pair_val]
            scene.play(
                *[FlashFill(d, ACCENT_FILL, scale_factor=1.18) for d in triple],
                *[FlashFill(d, RED, scale_factor=1.18) for d in pair],
                run_time=0.7,
            )
            colors = [ACCENT_FILL if d.value == triple_val else RED for d in dice]
            self.fly_to_box(scene, dice, colors, 8, 25)
        else:
            self.animate_zero_score(scene, 8, dice)

    def small_straight(self, scene, dice):
        present = {d.value for d in dice}
        run = next((s for s in ({1, 2, 3, 4}, {2, 3, 4, 5}, {3, 4, 5, 6}) if s <= present), None)
        if run:
            order = [next(d for d in dice if d.value == v) for v in sorted(run)]
            extra = [d for d in dice if d not in order]
            reorder_dice(scene, order + extra)
            colors = [RED, YELLOW, GREEN, BLUE]
            ascend_and_flash(scene, order, colors)
            self.fly_to_box(scene, order, colors, 9, 30)
        else:
            self.animate_zero_score(scene, 9, dice)

    def large_straight(self, scene, dice):
        present = {d.value for d in dice}
        if present in ({1, 2, 3, 4, 5}, {2, 3, 4, 5, 6}):
            order = [next(d for d in dice if d.value == v) for v in sorted(present)]
            reorder_dice(scene, order)
            colors = [RED, ORANGE, YELLOW, GREEN, BLUE]
            ascend_and_flash(scene, order, colors)
            self.fly_to_box(scene, order, colors, 10, 40)
        else:
            self.animate_zero_score(scene, 10, dice)

    def _resolve_square(self, square):
        if square is None:
            return self.yahtzee_bonus_point()
        if hasattr(square, "get_center"):
            return square.get_center()
        return square

    def yahtzee(self, scene, dice, bonus_square=None):
        """All five the same -> 50 the first time. On a later Yahtzee: a +100
        bonus (rainbow spin) if the box holds a real 50, or — if it was scratched
        to 0 — no bonus, just a plain spin toward the new cell. A non-Yahtzee
        scratches the box to 0. `bonus_square` (a value cell or point) is where
        extra Yahtzees are sent."""
        is_yahtzee = len({d.value for d in dice}) == 1

        if 11 not in self.value_texts:                     # Yahtzee box still open
            if is_yahtzee:
                reorder_dice(scene, dice)
                jump_and_spin(scene, dice)
                spin_into(scene, dice, self.yahtzee_box_point())
                self.animate_fixed_score(scene, 11, 50)
                self._yahtzee_is_50 = True
            else:
                self.animate_zero_score(scene, 11, dice)
            return

        if not is_yahtzee:
            return                                          # box already filled

        target = self._resolve_square(bonus_square)
        reorder_dice(scene, dice)
        if self._yahtzee_is_50:                             # real Yahtzee -> +100 bonus
            jump_and_spin(scene, dice, rainbow=True)
            spin_into(scene, dice, target, rainbow=True)
            self.animate_yahtzee_bonus(scene)
        else:                                               # scratched 0 -> no bonus
            jump_and_spin(scene, dice)
            spin_into(scene, dice, target)

    def chance(self, scene, dice):
        """Always the sum of all dice; pips fly in, no flash."""
        self.animate_bottom_score(scene, 12, dice)

    # ── totals helpers ─────────────────────────────────────────────────────────
    def _tick_total(self, scene, old_g, new_g, run_time):
        def total_for(g):
            t = crisp_text(str(int(round(g))), font_size=self.font_size, color=WHITE, font=FONT, weight="BOLD")
            t.move_to(self.total_text.get_center())
            return t

        tr = ValueTracker(old_g)
        self.total_text.add_updater(lambda m: m.become(total_for(tr.get_value())))
        scene.play(tr.animate.set_value(new_g), run_time=run_time)
        self.total_text.clear_updaters()
        self.total_text.become(total_for(new_g))

    def _top_total(self):
        return self._top_sum + (35 if self._top_sum >= 63 else 0)

    def _animate_top_total(self, scene, old, new, run_time):
        # One continuous rise (never pauses, even crossing 63); the green flash
        # fires afterward once the bar has reached its final height.
        past = old >= 63
        self._run_rise(scene, old, new, green=past, bonus=past, run_time=run_time)
        if old < 63 <= new:
            self._flash_63(scene, new)

    def _run_rise(self, scene, frm, to, *, green, bonus, run_time):
        bar_top = self.bar_border.get_top()[1]
        bar_bot = self.bar_border.get_bottom()[1]
        bar_h   = self.bar_border.height
        bar_cx  = self.bar_border.get_center()[0]
        bar_w   = self.bar_border.width
        ch      = self.cell_height
        fives_y = bar_top - 2.5 * ch
        base    = self._bottom_sum + self._yahtzee_bonus
        fcolor  = SCORE_GREEN if green else ACCENT_FILL

        def fill_for(v):
            h = max(bar_h * v / 63, 1e-4)   # keeps growing past 63 (overflow)
            r = Rectangle(width=bar_w, height=h, fill_color=fcolor,
                          fill_opacity=1.0, stroke_width=0)
            r.move_to(np.array([bar_cx, bar_bot + h / 2, 0]))
            return r

        def number_for(v):
            iv    = int(round(v))
            below = iv <= 21
            col   = BLACK if below else WHITE
            ftop  = bar_bot + bar_h * min(iv, 63) / 63
            y     = ftop + 0.4 * ch if below else fives_y
            t = crisp_text(str(iv), font_size=self.font_size, color=col, font=FONT, weight="BOLD")
            t.set_fill(col, opacity=1.0)
            t.move_to(np.array([bar_cx, y, 0]))
            return t

        def total_for(v):
            g = int(round(v)) + (35 if bonus else 0) + base
            t = crisp_text(str(g), font_size=self.font_size, color=WHITE, font=FONT, weight="BOLD")
            t.move_to(self.total_text.get_center())
            return t

        tr = ValueTracker(frm)
        self.bar_fill.add_updater(lambda m: m.become(fill_for(tr.get_value())))
        self.bar_number.add_updater(lambda m: m.become(number_for(tr.get_value())))
        self.total_text.add_updater(lambda m: m.become(total_for(tr.get_value())))
        scene.play(tr.animate.set_value(to), run_time=run_time)
        for m in (self.bar_fill, self.bar_number, self.total_text):
            m.clear_updaters()
        self.bar_fill.become(fill_for(to))
        self.bar_number.become(number_for(to))
        self.total_text.become(total_for(to))

    def _flash_63(self, scene, top_sum):
        bar_top = self.bar_border.get_top()[1]
        bar_cx  = self.bar_border.get_center()[0]
        ch      = self.cell_height
        base    = self._bottom_sum + self._yahtzee_bonus

        new_cap = crisp_text("(63)", font_size=self.font_size * 0.55, color=WHITE, font=FONT, weight="BOLD")
        new_cap.move_to(np.array([bar_cx, bar_top - 0.35 * ch, 0]))

        self.bonus_label = crisp_text("+35", font_size=self.font_size, color=SCORE_GREEN, font=FONT, weight="BOLD")
        self.bonus_label.move_to(np.array([bar_cx, bar_top - 3.5 * ch, 0]))

        new_total = crisp_text(str(top_sum + 35 + base), font_size=self.font_size, color=WHITE, font=FONT, weight="BOLD")
        new_total.move_to(self.total_text.get_center())

        scene.play(
            self.bar_fill.animate.set_fill(SCORE_GREEN, opacity=1.0),
            Flash(self.bar_border.get_center(), color=SCORE_GREEN, flash_radius=0.55, line_length=0.22),
            Transform(self.cap_label, new_cap),
            FadeIn(self.bonus_label, shift=0.25 * DOWN),
            Transform(self.total_text, new_total),
            run_time=0.8,
        )
        self.score_texts.add(self.bonus_label)

    def _animate_bottom_total(self, scene, old_b, new_b, run_time):
        def bottom_for(b):
            t = crisp_text(str(int(round(b))), font_size=self.font_size, color=BLACK, font=FONT, weight="BOLD")
            t.move_to(self.bottom_total_text.get_center())
            return t

        def total_for(b):
            g = self._top_total() + int(round(b)) + self._yahtzee_bonus
            t = crisp_text(str(g), font_size=self.font_size, color=WHITE, font=FONT, weight="BOLD")
            t.move_to(self.total_text.get_center())
            return t

        tr = ValueTracker(old_b)
        self.bottom_total_text.add_updater(lambda m: m.become(bottom_for(tr.get_value())))
        self.total_text.add_updater(lambda m: m.become(total_for(tr.get_value())))
        scene.play(tr.animate.set_value(new_b), run_time=run_time)
        for m in (self.bottom_total_text, self.total_text):
            m.clear_updaters()
        self.bottom_total_text.become(bottom_for(new_b))
        self.total_text.become(total_for(new_b))


def get_scorecard(scores=None, center=CENTER_SC, **kwargs):
    return Scorecard(scores=scores, center=center, **kwargs)
