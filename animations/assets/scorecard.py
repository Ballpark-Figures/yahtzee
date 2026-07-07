from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from manim import *
from config import *
from assets.dice import (
    FlashFill, reorder_dice, ascend_and_flash, jump_and_spin,
    spin_into_anim, reindex_dice, slot_x, BAND_YS,
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

    # Where the running counters start, as a fraction of the box/score animation
    # they overlap: the totals begin at COUNTER_LAG of that "lead" animation (so
    # they kick in a bit before it finishes, not after). EVERY scoring path routes
    # its counter through a `lead` so this is applied consistently. A feel knob.
    COUNTER_LAG = 0.7

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
        fourth_column=False,
        fourth_width=1.4,
    ):
        super().__init__()
        # show_summary=False removes the 3rd-column CONTENTS only (the (63) bar,
        # running totals, bottom total, grand total) — the column outline, the
        # box scores, and the Total footer bar all stay.
        self.show_summary = show_summary
        # Optional 4th column (scene 06): an extra outlined column to the RIGHT of
        # the summary column, for "other info" (a histogram in the top block, a
        # Prob/Avg pair in the bottom block). OFF by default so every other scene
        # is untouched. The asset only draws the empty column + exposes geometry
        # (col4_x/width, top/bottom regions, per-row anchor cells); the SCENE fills
        # it. Adding it widens full_width, so the whole card re-centers.
        self.fourth_column = fourth_column
        self.col4_width = fourth_width if fourth_column else None
        # row -> invisible anchor Rectangle; part of the card VGroup so it moves
        # with the card. Read live via col4_region()/col4_cells (never store the
        # build-time coords — the card gets move_to()'d after _build).
        self.col4_cells = {}
        self.cell_height = cell_height
        self.font_size   = font_size
        self.text_pad    = text_pad
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width

        # animatable handles
        self.value_cells = {}     # row -> value Rectangle
        self.label_cells = {}     # row -> label Rectangle (col 1)
        self.value_texts = {}     # row -> score Text
        self.value_nums  = {}     # row -> numeric score (for un-scoring/totals)
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
                    section_gap, bottom_gap, fourth_column, fourth_width)

        self.add(self.cells, self.labels, self.score_texts)
        # Keep all card text ABOVE any transient highlight fill (which sits at the
        # default z_index 0), so the (bold) label reads in front of the yellow,
        # not dimmed behind it.
        self.labels.set_z_index(1)
        self.score_texts.set_z_index(1)
        self.move_to(center)

    # ── Static build ─────────────────────────────────────────────────────────
    def _build(self, scores, label_width, value_width, summary_width,
               stroke_color, stroke_width, grid_color, grid_width,
               section_gap, bottom_gap, fourth_column=False, fourth_width=1.4):
        cell_height = self.cell_height
        font_size   = self.font_size
        text_pad    = self.text_pad
        cells, labels, score_texts = self.cells, self.labels, self.score_texts

        n = len(SCORE_ROWS)
        total_height = n * cell_height + section_gap + bottom_gap

        # slight breathing room: a gap below the YAHTZEE header (above row 1) and
        # above the Total footer (below the last row).
        header_gap = cell_height * 0.32
        footer_gap = cell_height * 0.32

        col4_w     = fourth_width if fourth_column else 0
        full_width = label_width + value_width + summary_width + col4_w
        left_edge  = -full_width / 2
        label_x    = left_edge + label_width / 2
        value_x    = left_edge + label_width + value_width / 2
        summary_x  = left_edge + label_width + value_width + summary_width / 2
        fourth_x   = summary_x + summary_width / 2 + col4_w / 2

        bottom_edge = total_height / 2 - (BOTTOM_START + BOTTOM_ROWS) * cell_height - section_gap
        total_y     = bottom_edge - cell_height / 2 - footer_gap

        # ── Card surface ─────────────────────────────────────────────────────
        grid_top    = total_height / 2
        header_h    = cell_height * 1.2
        header_cy   = grid_top + header_gap + header_h / 2

        panel_pad   = 0.18
        content_top = grid_top + header_gap + header_h
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
        # full content width + center x are reused by the row-highlight helpers
        self.header_rect = header
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
            self.label_cells[i] = label_cell

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

            if fourth_column:
                # invisible per-row anchor in col 4 (rides with the card, so the
                # scene can align content to each row without re-measuring)
                anchor = Rectangle(
                    width=col4_w, height=cell_height,
                    fill_opacity=0, stroke_width=0,
                ).move_to(np.array([fourth_x, y, 0]))
                self.col4_cells[i] = anchor
                cells.add(anchor)

            if c is not None:
                val, color, opacity = c["rows"][i]
                if val is not None:
                    sv = crisp_text(str(val), font_size=font_size, color=color, font=FONT)
                    sv.set_fill(color, opacity=opacity)
                    sv.move_to(np.array([value_x, y, 0]))
                    score_texts.add(sv)
                    self.value_texts[i] = sv
                    self.value_nums[i] = val

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
            # Summary always renders full-strength. (We used to dim an incomplete
            # section's totals to 0.5, but the animator never re-applied it, so any
            # scored card was full anyway — the dimming only ever showed on a
            # freshly-built static mid-game card and read as inconsistent.)
            top_opacity = 1.0

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

        # ── Optional 4th column (top block + bottom block, mirroring summary) ──
        if fourth_column:
            cells.add(Rectangle(
                width=col4_w, height=top_h,
                fill_opacity=0, stroke_color=grid_color, stroke_width=grid_width,
            ).move_to(np.array([fourth_x, top_summary_cy, 0])))
            cells.add(Rectangle(
                width=col4_w, height=bottom_h,
                fill_opacity=0, stroke_color=grid_color, stroke_width=grid_width,
            ).move_to(np.array([fourth_x, bottom_summary_cy, 0])))

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
            bottom_opacity = 1.0

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

            self.total_text = crisp_text(str(grand_total), font_size=font_size, color=WHITE, font=FONT, weight="BOLD")
            self.total_text.set_fill(WHITE, opacity=1.0)
            self.total_text.move_to(np.array([summary_x, total_y, 0]))
            score_texts.add(self.total_text)

    # ── 4th column geometry (live, tracks the card's current position) ─────────
    def col4_region(self, rows):
        """Absolute (center, width, height) spanning the col-4 anchor `rows`
        (an iterable of row indices). Computed from the live anchor cells, so it
        is correct AFTER the card has been move_to()'d. Use for the top block
        (rows 0..5) or bottom block (rows 6..12); per-row placement is
        `col4_cells[i].get_center()`."""
        cells = [self.col4_cells[r] for r in rows]
        top = max(c.get_top()[1] for c in cells)
        bot = min(c.get_bottom()[1] for c in cells)
        x = cells[0].get_center()[0]
        return np.array([x, (top + bot) / 2, 0]), self.col4_width, (top - bot)

    # ── Row highlighting ───────────────────────────────────────────────────────
    def _row_highlight(self, row, color, opacity):
        """The transient highlight pieces for `row`: a soft fill + a thick black
        border over the label+value pair (columns 1-2 ONLY, not the summary
        column), and a BOLD copy of the row label sitting exactly over the
        original. Returns (fill, border, bold_label). Built in global coords; not
        added to the card."""
        lcell = self.label_cells[row]
        vcell = self.value_cells[row]
        left  = lcell.get_left()[0]
        right = vcell.get_right()[0]
        width = right - left
        cx    = (left + right) / 2
        y     = vcell.get_center()[1]

        fill = Rectangle(
            width=width, height=self.cell_height, stroke_width=0,
            fill_color=color, fill_opacity=opacity,
        ).move_to(np.array([cx, y, 0]))
        border = Rectangle(
            width=width, height=self.cell_height, fill_opacity=0,
            stroke_color=BLACK, stroke_width=self.stroke_width * 3,
        ).move_to(np.array([cx, y, 0]))

        lbl = self.labels[row]
        bold_lbl = crisp_text(SCORE_ROWS[row], font_size=self.font_size,
                              color=BLACK, font=FONT, weight="BOLD")
        bold_lbl.align_to(lbl, LEFT).set_y(lbl.get_center()[1])
        return fill, border, bold_lbl

    def highlight_rows(self, scene, rows, *, color=ACCENT_GOLD, opacity=0.45,
                       run_time=None, fade=0.25, hold=1.0, lag_ratio=0.0,
                       pulse=False):
        """Emphasise whole scorecard rows (label+value, columns 1-2): a soft fill
        + thick border, with the row label bolded.

        Default HOLDS the highlight — fade in, hold for `hold` s, fade out — the
        steady emphasis the video wants. `pulse=True` instead flashes each row
        there-and-back (use `lag_ratio` > 0 to WALK the flash down the rows). For
        back-compat, a `run_time` is taken as the pulse duration, or (holding) as
        the hold duration. Transient — nothing is left on the card afterward."""
        rows   = list(rows)
        pieces = [self._row_highlight(r, color, opacity) for r in rows]

        if pulse:
            rt = run_time if run_time is not None else 0.8
            anims = [AnimationGroup(
                        FadeIn(fill,   rate_func=there_and_back),
                        FadeIn(border, rate_func=there_and_back),
                        Transform(self.labels[r], bold, rate_func=there_and_back),
                     ) for (fill, border, bold), r in zip(pieces, rows)]
            scene.play(LaggedStart(*anims, lag_ratio=lag_ratio), run_time=rt)
            for fill, border, _bold in pieces:
                scene.remove(fill, border)
            return

        hold = run_time if run_time is not None else hold
        for r in rows:
            self.labels[r].save_state()
        scene.play(
            LaggedStart(*[AnimationGroup(FadeIn(fill), FadeIn(border),
                                         Transform(self.labels[r], bold))
                          for (fill, border, bold), r in zip(pieces, rows)],
                        lag_ratio=lag_ratio),
            run_time=fade,
        )
        scene.wait(hold)
        scene.play(
            *[FadeOut(fill) for fill, _b, _bold in pieces],
            *[FadeOut(border) for _f, border, _bold in pieces],
            *[Restore(self.labels[r]) for r in rows],
            run_time=fade,
        )
        for fill, border, _bold in pieces:
            scene.remove(fill, border)

    def flash_rows(self, scene, entries, *, color=ACCENT_GOLD, opacity=0.45,
                   fade=0.25, hold=0.9, lag_ratio=0.0):
        """Like highlight_rows, but each entry may carry a black number in its
        value cell that fades in/out IN SYNC with the highlight, then is removed —
        the number only exists during the flash and the committed cell contents
        are untouched. `entries` = [(row, value|None), …]. Highlight defaults to
        ACCENT_GOLD (our standard emphasis); pass color=SCORE_RED for a "don't do
        this" demo."""
        entries = list(entries)
        rows = [r for r, _ in entries]
        pieces = [self._row_highlight(r, color, opacity) for r in rows]
        nums = []
        for row, value in entries:
            if value is not None:
                n = crisp_text(str(value), font_size=self.font_size,
                               color=BLACK, font=FONT)
                n.move_to(self.value_cells[row].get_center())
                nums.append(n)
        for r in rows:
            self.labels[r].save_state()
        scene.play(
            LaggedStart(*[AnimationGroup(FadeIn(fill), FadeIn(border),
                                         Transform(self.labels[r], bold))
                          for (fill, border, bold), r in zip(pieces, rows)],
                        lag_ratio=lag_ratio),
            *[FadeIn(n) for n in nums],
            run_time=fade,
        )
        scene.wait(hold)
        scene.play(
            *[FadeOut(fill) for fill, _b, _bold in pieces],
            *[FadeOut(border) for _f, border, _bold in pieces],
            *[Restore(self.labels[r]) for r in rows],
            *[FadeOut(n) for n in nums],
            run_time=fade,
        )
        for fill, border, _bold in pieces:
            scene.remove(fill, border)
        for n in nums:
            scene.remove(n)

    # ── PERSISTENT row highlight (raise it, hold across many plays, drop it) ────
    # For "this box stays lit for the WHOLE beat": raise at the start, release at
    # the end. Unlike highlight_rows (which fades itself out after a hold), the
    # hold persists until release_rows(). Promoted from scene 06's private helper.
    def hold_rows(self, scene, rows, *, color=ACCENT_GOLD, run_time=0.35):
        """Raise a persistent highlight on `rows`, DROPPING any prior hold first."""
        self.release_rows(scene, run_time=0.0)
        self.extend_hold(scene, rows, color=color, run_time=run_time)

    def extend_hold(self, scene, rows, *, color=ACCENT_GOLD, run_time=0.35):
        """Add `rows` to the current hold without dropping what's already held."""
        anims = self.hold_rows_anims(rows, color=color)
        if anims:
            scene.play(*anims, run_time=run_time)

    def hold_rows_anims(self, rows, *, color=ACCENT_GOLD):
        """Build + register a hold on `rows` and RETURN the raise anims (instead of
        playing them), so a caller can fold the highlight into another play — e.g.
        raise it in lockstep with a card swap. Does not drop existing holds."""
        rows = [rows] if isinstance(rows, int) else list(rows)
        held = list(getattr(self, "_held", None) or [])
        existing = {r for _, _, r in held}
        anims = []
        for r in rows:
            if r in existing:
                continue
            fill, border, bold = self._row_highlight(r, color, 0.45)
            self.labels[r].save_state()
            anims += [FadeIn(fill), FadeIn(border), Transform(self.labels[r], bold)]
            held.append((fill, border, r))
        self._held = held
        return anims

    def held_pieces(self):
        """The (fill, border) mobjects currently held — for a caller that hard-
        clears the scene and must KEEP the live highlight."""
        return [(f, b) for f, b, _r in (getattr(self, "_held", None) or [])]

    def release_rows(self, scene, rows=None, *, run_time=0.3):
        """Release held rows — ALL by default, or just the given subset (leaving
        the rest of the hold up). No-op if nothing is held."""
        held = getattr(self, "_held", None)
        if not held:
            return
        want = None if rows is None else ({rows} if isinstance(rows, int) else set(rows))
        drop = [p for p in held if want is None or p[2] in want]
        keep = [p for p in held if not (want is None or p[2] in want)]
        if run_time > 0 and drop:
            scene.play(*[a for fill, border, r in drop
                         for a in (FadeOut(fill), FadeOut(border), Restore(self.labels[r]))],
                       run_time=run_time)
        else:
            for _fill, _border, r in drop:
                self.labels[r].restore()
        for fill, border, _r in drop:
            scene.remove(fill, border)
        self._held = keep or None

    def slide_in(self, scene, *, from_dir=LEFT, dist=None, run_time=1.0, lead=None,
                 play=True):
        """The STANDARD scorecard entrance: slide it in from `from_dir` (DEFAULT:
        from the LEFT side) — shift it fully off-screen in that direction, add it,
        then animate back to its home position. Use this everywhere instead of
        hand-rolling an entrance; an opacity fade corrupts the (63) bar (see
        CLAUDE.md), so we always SLIDE. `dist=None` auto-computes the smallest
        shift that starts the card just past the real frame edge; pass an explicit
        `dist` to override. `lead` plays other anims (e.g. dice) with the slide."""
        d = np.array(from_dir, dtype=float)
        norm = np.linalg.norm(d)
        if norm:
            d = d / norm
        home = self.get_center().copy()
        if dist is None:
            fx, fy, margin = config.frame_x_radius, config.frame_y_radius, 0.4
            if abs(d[0]) >= abs(d[1]):                     # horizontal slide
                dist = (home[0] if d[0] < 0 else -home[0]) + self.width / 2 + fx
            else:                                          # vertical slide
                dist = (home[1] if d[1] < 0 else -home[1]) + self.height / 2 + fy
            dist += margin
        self.shift(d * dist)
        scene.add(self)
        move = self.animate.move_to(home)
        if not play:
            return move          # caller composes it into a bigger play (e.g. a pair)
        anims = [move]
        if lead is not None:
            anims += list(lead) if isinstance(lead, (list, tuple)) else [lead]
        scene.play(*anims, run_time=run_time)
        return self

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
            lead = ReplacementTransform(pip_copies, number)
        else:
            lead = FadeIn(number)
        self.value_texts[row] = number
        self.value_nums[row]  = add

        # 3. raise the bar + count the totals (the counter overlaps the fly-in via
        #    `lead`; flashes green when crossing 63)
        self._animate_top_total(scene, old, new, run_time, lead=lead)
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
            lead = ReplacementTransform(pip_copies, number)
        else:
            lead = FadeIn(number)
        self.value_texts[row] = number
        self.value_nums[row]  = score

        # 3. tick the bottom total + grand total (overlapping the fly-in)
        old_b, new_b = self._bottom_sum, self._bottom_sum + score
        self._animate_bottom_total(scene, old_b, new_b, run_time, lead=lead)
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
        lead = AnimationGroup(FadeIn(hl, rate_func=there_and_back), GrowFromCenter(number))
        self.value_texts[row] = number
        self.value_nums[row]  = score

        old_b, new_b = self._bottom_sum, self._bottom_sum + score
        self._animate_bottom_total(scene, old_b, new_b, run_time, lead=lead)
        self._bottom_sum = new_b
        scene.remove(hl)

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
        self.value_nums[row]  = 0

    def fly_to_box(self, scene, dice, colors, row, score, *, run_time=1.0,
                   hide_pips=False, return_dice=None, return_y=None):
        """For color categories: tint copies of `dice` with `colors` (None = leave
        as-is) and fly them into the value box, morphing into the score; then tick
        the bottom total + grand total.

        hide_pips    -> the flying copies show only the colored die BODIES, no pips.
        return_dice  -> these real dice slide back to their home slots (by list
                        index) in the SAME play, so they start returning as soon as
                        the colored boxes begin moving off. `return_y` overrides
                        the band-3 height (used by the centered-dice presentation).
        The running counters overlap the fly via `lead` (see COUNTER_LAG)."""
        cell   = self.value_cells[row]
        number = crisp_text(str(score), font_size=self.font_size, color=BLACK, font=FONT)
        number.move_to(cell.get_center())

        group = VGroup()
        for d, c in zip(dice, colors):
            cp = d.copy()
            if c is not None:
                cp.body.set_fill(ManimColor(c), opacity=1.0)
            if hide_pips:
                cp.pips.set_opacity(0.0)
            group.add(cp)

        scene.add(group)
        fly = ReplacementTransform(group, number)
        if return_dice is not None:
            yy = BAND_YS[3] if return_y is None else return_y
            # dice slide home AND restore full opacity in the same motion, so any
            # die grayed for this category (e.g. the small-straight odd die) un-fades
            # as it returns rather than in a separate step afterward.
            returns = [d.animate.move_to([slot_x(i), yy, 0]).set_opacity(1.0)
                       for i, d in enumerate(return_dice)]
            lead = AnimationGroup(fly, *returns)
        else:
            lead = fly
        self.value_texts[row] = number
        self.value_nums[row]  = score

        old_b, new_b = self._bottom_sum, self._bottom_sum + score
        self._animate_bottom_total(scene, old_b, new_b, run_time, lead=lead)
        self._bottom_sum = new_b

    def yahtzee_box_point(self):
        return self.value_cells[YAHTZEE_IDX].get_center()

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
            # only the colored boxes fly into the Full House box — not the pips
            self.fly_to_box(scene, dice, colors, 8, 25, hide_pips=True)
        else:
            self.animate_zero_score(scene, 8, dice)

    def small_straight(self, scene, dice, *, y=None, score=True):
        """Score the small straight, OR (score=False) just PREVIEW it — rearrange
        the run into the ascending staircase and flash the colors, with no box
        fill / total change (used to say "you've got a small straight here")."""
        present = {d.value for d in dice}
        run = next((s for s in ({1, 2, 3, 4}, {2, 3, 4, 5}, {3, 4, 5, 6}) if s <= present), None)
        if run:
            order = [next(d for d in dice if d.value == v) for v in sorted(run)]
            extra = [d for d in dice if d not in order]
            new = order + extra
            # gray the unused die(s) for the duration of the straight — part of the
            # animation itself (set_opacity(0.25), same fade as always). They un-fade
            # automatically during the dice return inside fly_to_box.
            if extra:
                scene.play(*[d.animate.set_opacity(0.25) for d in extra], run_time=0.4)
            # rearrange ONCE into the run order, then reindex (die in slot 0 becomes
            # die 0, …) so the dice stay where they are — nothing moves back.
            reorder_dice(scene, new, y=y)
            reindex_dice(dice, new)
            colors = [RED, YELLOW, GREEN, BLUE]
            ascend_and_flash(scene, order, colors, y=y)   # vertical staircase + flash
            if not score:
                return                                    # preview only — no box fill
            # colored boxes fly off while the dice settle back into a flat horizontal
            # line AND restore opacity (the unused die un-fades as it returns).
            self.fly_to_box(scene, order, colors, 9, 30,
                            hide_pips=True, return_dice=dice, return_y=y)
        elif score:
            self.animate_zero_score(scene, 9, dice)

    def large_straight(self, scene, dice, *, y=None):
        present = {d.value for d in dice}
        if present in ({1, 2, 3, 4, 5}, {2, 3, 4, 5, 6}):
            order = [next(d for d in dice if d.value == v) for v in sorted(present)]
            reorder_dice(scene, order, y=y)
            reindex_dice(dice, order)
            colors = [RED, ORANGE, YELLOW, GREEN, BLUE]
            ascend_and_flash(scene, order, colors, y=y)   # vertical staircase + flash
            self.fly_to_box(scene, order, colors, 10, 40,
                            hide_pips=True, return_dice=dice, return_y=y)
        else:
            self.animate_zero_score(scene, 10, dice)

    def yahtzee(self, scene, dice, *, y=None):
        """Score the still-open Yahtzee box: five-of-a-kind → 50 with a jump-spin
        into the box (and the box becomes bonus-eligible); otherwise scratch it to
        0. Later bonus Yahtzees are handled by `joker_fill`, which reads
        `_yahtzee_is_50` to decide on the rainbow flourish + the +100."""
        if len({d.value for d in dice}) == 1:
            reorder_dice(scene, dice, y=y)
            jump_and_spin(scene, dice)
            self._fill_via_spin(scene, dice, 11, 50, self.yahtzee_box_point())
            self._yahtzee_is_50 = True
        else:
            self.animate_zero_score(scene, 11, dice)

    def chance(self, scene, dice):
        """Always the sum of all dice; pips fly in, no flash."""
        self.animate_bottom_score(scene, 12, dice)

    # ── Un-scoring + joker / endgame edits ─────────────────────────────────────
    def reset(self, scene, *, run_time=0.8):
        """Empty the whole card back to blank — SAME card object — fading every
        filled value out while the bar + all totals reverse down to 0. Used to
        wipe the mechanics demo (a–c) before the systematic box walkthrough."""
        fades = [FadeOut(t) for t in self.value_texts.values()]
        lead  = AnimationGroup(*fades) if fades else None
        self.value_texts    = {}
        self.value_nums     = {}
        self._yahtzee_is_50 = False
        self._animate_to(scene, top=0, bottom=0, ybonus=0, lead=lead, run_time=run_time)

    def _fill_via_spin(self, scene, dice, row, score, target, *, rainbow=False,
                       turns=2, flash_color=YELLOW, run_time=1.1):
        """Fly the dice into `target` (a spin-shrink) AS the counter's lead: the
        box number grows in as the dice arrive and the bottom + grand totals
        overlap the FLIGHT (so the counter doesn't wait for the dice to land).
        Shared by the Yahtzee and Joker box fills."""
        copies, fly = spin_into_anim(scene, dice, target, rainbow=rainbow, turns=turns)
        cell   = self.value_cells[row]
        number = crisp_text(str(score), font_size=self.font_size, color=BLACK, font=FONT)
        number.move_to(cell.get_center())
        hl = cell.copy()
        hl.set_fill(flash_color, opacity=0.7)
        hl.set_stroke(width=0)
        scene.add(hl)
        # the number pops in at the TAIL of the flight (as the dice arrive), not
        # growing throughout it; the counter still overlaps the flight via `lead`.
        reveal = Succession(Wait(0.6),
                            AnimationGroup(FadeIn(hl, rate_func=there_and_back),
                                           GrowFromCenter(number)))
        lead = AnimationGroup(fly, reveal)
        self.value_texts[row] = number
        self.value_nums[row]  = score
        old_b, new_b = self._bottom_sum, self._bottom_sum + score
        self._animate_bottom_total(scene, old_b, new_b, run_time, lead=lead)
        self._bottom_sum = new_b
        scene.remove(hl, *copies)

    def joker_fill(self, scene, dice, row, score, *, y=None, run_time=1.1):
        """Fill `row` with `score` via a Joker Yahtzee. The card chooses everything
        from its OWN state (`_yahtzee_is_50`): a real-50 Yahtzee (bonus-eligible)
        gets the full rainbow JUMP-spin AND a +100 bonus; a scratched-0 Yahtzee
        gets a plain spin-in-place → glide and no bonus. Works for an upper box
        (raises the bar) or a lower box (raises the bottom total), chosen by `row`.
        The score pops in at the tail of the flight; the counters overlap it."""
        bonus  = self._yahtzee_is_50
        target = self.value_cells[row].get_center()
        reorder_dice(scene, dice, y=y)
        if bonus:
            jump_and_spin(scene, dice, rainbow=True)            # jump + spin + rainbow
            copies, fly = spin_into_anim(scene, dice, target, rainbow=True, turns=2)
        else:
            jump_and_spin(scene, dice, bump=0.0)                # spin in place, no jump
            copies, fly = spin_into_anim(scene, dice, target, turns=0)   # glide, no spin

        number = crisp_text(str(score), font_size=self.font_size, color=BLACK, font=FONT)
        number.move_to(target)
        hl = self.value_cells[row].copy()
        hl.set_fill(YELLOW, opacity=0.7)
        hl.set_stroke(width=0)
        scene.add(hl)
        reveal = Succession(Wait(0.6),
                            AnimationGroup(FadeIn(hl, rate_func=there_and_back),
                                           GrowFromCenter(number)))
        lead = AnimationGroup(fly, reveal)
        self.value_texts[row] = number
        self.value_nums[row]  = score
        self._animate_to(
            scene, lead=lead, run_time=run_time,
            top=(self._top_sum + score) if row < BOTTOM_START else None,
            bottom=(self._bottom_sum + score) if row >= BOTTOM_START else None,
            ybonus=(self._yahtzee_bonus + 100) if bonus else None,
        )
        scene.remove(hl, *copies)

    def transition(self, scene, changes, *, run_time=1.1, flash=True):
        """Transition the card to a new state declaratively, in ONE play. `changes`
        maps a row to its new value: an int sets/replaces the cell (shown as a
        plain number, e.g. 0 for a scratch); None clears the cell. The top/bottom
        sums are recomputed from the deltas and the cells + bar + counters animate
        together (via `_animate_to`). This is for plain state edits — clearing,
        scratching, replacing a value; the fancy demo flourishes (pips flying,
        dice spinning, colored boxes) build their own `lead` and call `_animate_to`
        directly."""
        fades   = []
        new_top = self._top_sum
        new_bot = self._bottom_sum
        for row, val in changes.items():
            old_val = self.value_nums.get(row, 0)
            delta   = (0 if val is None else val) - old_val
            if row < BOTTOM_START:
                new_top += delta
            else:
                new_bot += delta
            num = self.value_texts.get(row)
            if val is None:                              # clear the cell
                if num is not None:
                    fades.append(FadeOut(num))
                self.value_texts.pop(row, None)
                self.value_nums.pop(row, None)
            else:                                        # set / replace the value
                new_text = crisp_text(str(val), font_size=self.font_size, color=BLACK, font=FONT)
                new_text.move_to(self.value_cells[row].get_center())
                if num is not None:
                    fades.append(Transform(num, new_text))   # morph in place
                else:
                    scene.add(new_text)
                    fades.append(FadeIn(new_text))
                    self.value_texts[row] = new_text
                self.value_nums[row] = val
            if row == YAHTZEE_IDX:
                self._yahtzee_is_50 = (val == 50)

        lead = AnimationGroup(*fades) if fades else None
        self._animate_to(scene, top=new_top, bottom=new_bot, lead=lead,
                         run_time=run_time, flash=flash)

    # ── totals helpers ─────────────────────────────────────────────────────────
    # Thin wrappers over the one animator, kept so the per-category scoring
    # methods read naturally.
    def _animate_top_total(self, scene, old, new, run_time, *, lead=None):
        self._animate_to(scene, top=new, lead=lead, run_time=run_time)

    def _animate_bottom_total(self, scene, old_b, new_b, run_time, *, lead=None):
        self._animate_to(scene, bottom=new_b, lead=lead, run_time=run_time)

    def _animate_to(self, scene, *, top=None, bottom=None, ybonus=None,
                    lead=None, run_time=1.1, flash=True):
        """THE counter/bar animator. Moves the top sum, bottom sum, and Yahtzee
        bonus from their current values to the given targets (any left None is
        unchanged) in ONE play, driven by value off three trackers:

          • top bar    — height grows/shrinks; fill is green iff value >= 63;
                         the "(63)" cap sits above the bar (black) below 63 and
                         drops inside the bar top (white) at/above 63; the +35
                         label fades in/out at 63; an UPWARD crossing fires a
                         green Flash burst (when `flash`).
          • bottom sum — the bottom total text.
          • Yahtzee +100 — the running "+N" label is grown/updated.
          • grand total — recomputed from all three every frame.

        `lead` (the cell-level visual: pips flying, dice spinning, a fade, …)
        overlaps the count via COUNTER_LAG. This is the ONLY place the bar and
        the totals are animated; every scoring/un-scoring path routes through it."""
        old_top, old_bot, old_yb = self._top_sum, self._bottom_sum, self._yahtzee_bonus
        new_top = old_top if top    is None else top
        new_bot = old_bot if bottom is None else bottom
        new_yb  = old_yb  if ybonus is None else ybonus

        bar_top = self.bar_border.get_top()[1]
        bar_bot = self.bar_border.get_bottom()[1]
        bar_h   = self.bar_border.height
        bar_cx  = self.bar_border.get_center()[0]
        bar_w   = self.bar_border.width
        ch      = self.cell_height
        fives_y = bar_top - 2.5 * ch
        green_c = ManimColor(SCORE_GREEN)

        tr_top = ValueTracker(old_top)
        tr_bot = ValueTracker(old_bot)
        tr_yb  = ValueTracker(old_yb)

        # Bar colour matches the static build: GREEN once the bonus is earned
        # (>= 63); else RED if the top section is COMPLETE but under 63 (finished
        # the top, missed the bonus); else blue (still in progress). top_complete
        # is fixed for this animation (value_nums is updated before _animate_to).
        red_c = ManimColor(SCORE_RED)
        top_complete = all(r in self.value_nums for r in range(6))

        def color_at(v):
            if v >= 63:
                return green_c
            # Red only once the top's FINAL (complete) sum is reached. While a
            # score that completes the top is still counting in (v below new_top),
            # stay blue — so it flips red at the END of the grow, not the start.
            if top_complete and v >= new_top - 1e-6:
                return red_c
            return ACCENT_FILL

        def fill_for(v):
            h = max(bar_h * v / 63, 1e-4)   # keeps growing past 63 (overflow)
            r = Rectangle(width=bar_w, height=h, fill_color=color_at(v),
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

        def bottom_for(b):
            t = crisp_text(str(int(round(b))), font_size=self.font_size, color=BLACK, font=FONT, weight="BOLD")
            t.move_to(self.bottom_total_text.get_center())
            return t

        def grand_for():
            tv, bv, yv = tr_top.get_value(), tr_bot.get_value(), tr_yb.get_value()
            g = int(round(tv)) + (35 if tv >= 63 else 0) + int(round(bv)) + int(round(yv))
            t = crisp_text(str(g), font_size=self.font_size, color=WHITE, font=FONT, weight="BOLD")
            t.move_to(self.total_text.get_center())
            return t

        self.bar_fill.add_updater(lambda m: m.become(fill_for(tr_top.get_value())))
        self.bar_number.add_updater(lambda m: m.become(number_for(tr_top.get_value())))
        self.bottom_total_text.add_updater(lambda m: m.become(bottom_for(tr_bot.get_value())))
        self.total_text.add_updater(lambda m: m.become(grand_for()))

        # +35 top-bonus label (created the first time we cross up into the bonus)
        crossing_up = old_top < 63 <= new_top
        sixes_y     = bar_bot - 0.5 * ch
        if self.bonus_label is None and crossing_up:
            self.bonus_label = crisp_text("+35", font_size=self.font_size, color=SCORE_GREEN, font=FONT, weight="BOLD")
            self.bonus_label.move_to(np.array([bar_cx, sixes_y, 0])).set_opacity(0.0)
            self.score_texts.add(self.bonus_label)
        if self.bonus_label is not None:
            self.bonus_label.add_updater(
                lambda m: m.set_opacity(1.0 if tr_top.get_value() >= 63 else 0.0))

        # "(63)" cap: above the bar (black) below 63, inside the bar top (white) at/above
        black_cap = crisp_text("(63)", font_size=self.font_size * 0.55, color=BLACK, font=FONT, weight="BOLD")
        black_cap.move_to(np.array([bar_cx, bar_top + 0.35 * ch, 0]))
        white_cap = crisp_text("(63)", font_size=self.font_size * 0.55, color=WHITE, font=FONT, weight="BOLD")
        white_cap.move_to(np.array([bar_cx, bar_top - 0.35 * ch, 0]))
        self.cap_label.add_updater(
            lambda m: m.become(white_cap if tr_top.get_value() >= 63 else black_cap))

        # Yahtzee +100 label (discrete): grown/updated as part of the lead
        leads = [lead] if lead is not None else []
        if new_yb != old_yb and new_yb > 0:
            yb_y     = self.value_cells[YAHTZEE_IDX].get_center()[1]
            yb_label = crisp_text(f"+{new_yb}", font_size=self.font_size, color=SCORE_GREEN, font=FONT, weight="BOLD")
            yb_label.move_to(np.array([bar_cx, yb_y, 0]))
            if self.yahtzee_bonus_text is None:
                self.yahtzee_bonus_text = yb_label
                self.score_texts.add(yb_label)
                leads.append(AnimationGroup(GrowFromCenter(yb_label),
                                            Flash(yb_label.get_center(), color=SCORE_GREEN, flash_radius=0.5)))
            else:
                leads.append(AnimationGroup(Transform(self.yahtzee_bonus_text, yb_label),
                                            Flash(self.yahtzee_bonus_text.get_center(), color=SCORE_GREEN, flash_radius=0.5)))
        elif new_yb == 0 and self.yahtzee_bonus_text is not None:    # cleared (e.g. reset)
            leads.append(FadeOut(self.yahtzee_bonus_text))
            self.yahtzee_bonus_text = None

        moves = AnimationGroup(tr_top.animate.set_value(new_top),
                               tr_bot.animate.set_value(new_bot),
                               tr_yb.animate.set_value(new_yb))

        # Green spark burst as the bar crosses UP through 63. It TRIGGERS by value
        # (the moment the bar reaches 63) but then plays for a FIXED duration off
        # real elapsed time (dt) — so its speed is independent of how fast the bar
        # is rising. Never early (nothing below 63), never twice, and only when the
        # bonus is actually (re)earned.
        FLASH_DUR = 0.5     # fixed burst length (feel knob), independent of bar speed
        spark = None
        spark_t = {"v": None}     # elapsed since trigger; None = not yet triggered
        if flash and crossing_up and new_top > old_top:
            bc   = self.bar_border.get_center()
            # short radial dashes sitting just OUTSIDE the bar (so they're never
            # hidden behind it), in 12 directions.
            dirs = [np.array([np.cos(i * TAU / 12), np.sin(i * TAU / 12), 0.0]) for i in range(12)]
            base = VGroup(*[Line(bc + 0.34 * d, bc + 0.66 * d, stroke_color=green_c,
                                 stroke_width=4) for d in dirs])
            spark = base.copy().set_opacity(0.0)
            scene.add(spark)

            def _spark(m, dt):
                if spark_t["v"] is None:
                    if tr_top.get_value() >= 63:
                        spark_t["v"] = 0.0        # trigger the instant the bar hits 63
                    else:
                        return
                else:
                    spark_t["v"] += dt
                p = spark_t["v"] / FLASH_DUR       # fixed-duration progress (not bar-speed)
                if p >= 1.0:
                    m.set_opacity(0.0)
                    return
                m.become(base.copy().scale(1.0 + 0.35 * p, about_point=bc)   # gentle radiate
                         .set_stroke(green_c, width=4).set_opacity(np.sin(np.pi * p)))  # in→out
            spark.add_updater(_spark)

        full_lead = AnimationGroup(*leads) if len(leads) > 1 else (leads[0] if leads else None)
        if full_lead is not None:
            scene.play(LaggedStart(full_lead, moves, lag_ratio=self.COUNTER_LAG), run_time=run_time)
        else:
            scene.play(moves, run_time=run_time)

        # finalize the counters (bar has reached its target)
        for m in (self.bar_fill, self.bar_number, self.bottom_total_text,
                  self.total_text, self.cap_label):
            m.clear_updaters()
        if self.bonus_label is not None:
            self.bonus_label.clear_updaters()
            self.bonus_label.set_opacity(1.0 if new_top >= 63 else 0.0)
        self.cap_label.become(white_cap if new_top >= 63 else black_cap)
        self.bar_fill.become(fill_for(new_top))
        self.bar_number.become(number_for(new_top))
        self.bottom_total_text.become(bottom_for(new_bot))
        self.total_text.become(grand_for())
        self._top_sum, self._bottom_sum, self._yahtzee_bonus = new_top, new_bot, new_yb

        # let the fixed-duration flash finish if the bar settled before it did
        # (the bar is done; this is just the spark's tail)
        if spark is not None:
            if spark_t["v"] is not None and spark_t["v"] < FLASH_DUR:
                scene.wait(FLASH_DUR - spark_t["v"])
            spark.clear_updaters()
            scene.remove(spark)


def get_scorecard(scores=None, center=CENTER_SC, **kwargs):
    return Scorecard(scores=scores, center=center, **kwargs)
