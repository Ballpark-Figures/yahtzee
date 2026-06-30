from pathlib import Path
import sys
from itertools import combinations_with_replacement
from math import factorial

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from config import *
from assets.dice import (get_die, slot_point, slot_x, RollDie, roll_lines,
                         BAND_YS, PIP_COLORS)
from assets.scorecard import get_scorecard


# ── the 252 distinct outcomes, in the model's canonical (np.unique) order ──────
def _all_outcomes():
    """(values_tuple, n_arrangements) for each of the 252 distinct 5-dice rolls,
    sorted by face-count vector (same order the solver uses)."""
    rows = []
    for combo in combinations_with_replacement(range(1, 7), 5):
        vec = [combo.count(f) for f in range(1, 7)]
        ways = factorial(5)
        for c in vec:
            ways //= factorial(c)
        rows.append((tuple(vec), combo, ways))
    rows.sort(key=lambda r: r[0])           # np.unique-style lexicographic sort
    return [(combo, ways) for _, combo, ways in rows]


# canonical ascending k-multisets of 1..6 (e.g. k=2 -> (1,1),(1,2),...,(6,6))
def _multisets(k):
    return list(combinations_with_replacement(range(1, 7), k))


def _logfrac(v, lo, hi):
    """Fraction (0..1) of v between lo and hi on a log scale."""
    import math
    v = max(v, lo)
    return (math.log(v) - math.log(lo)) / (math.log(hi) - math.log(lo))


def _lerp(a, b, t):
    return [a[i] + (b[i] - a[i]) * t for i in range(3)]


def _random_scorecard(seed):
    """A valid, fully-filled scorecard (seeded -> deterministic for snapshots).
    scores[0..5] = Ones..Sixes (0..5 of that face), scores[6..12] =
    3oak/4oak/full house/sm straight/lg straight/yahtzee/chance, scores[13] =
    yahtzee bonus."""
    import random as _r
    rng = _r.Random(seed)
    s = []
    for face in range(1, 7):                       # top: 0..5 of each face
        s.append(rng.randint(0, 5) * face)
    s.append(rng.choice([0, 0] + list(range(8, 26))))   # 3 of a kind (sum or 0)
    s.append(rng.choice([0, 0] + list(range(10, 30))))  # 4 of a kind
    s.append(rng.choice([0, 25, 25]))              # full house
    s.append(rng.choice([0, 30, 30]))              # small straight
    s.append(rng.choice([0, 0, 40]))               # large straight
    s.append(rng.choice([0, 0, 0, 50]))            # yahtzee
    s.append(rng.randint(5, 30))                   # chance (always a sum)
    s.append(0)                                    # yahtzee bonus
    return s


# grid shape (rows, cols) used for each build-up step's count
_GRID_SHAPE = {6: (2, 3), 21: (3, 7), 56: (8, 7), 126: (14, 9), 252: (21, 12)}

# Equal margins: same gap on all sides of the 16x9 frame. Width fills to
# 16 - 2*margin; _balance_rows then stretches rows to the matching height so
# the vertical margin equals the horizontal one.
_MARGIN = 0.15
_FIT_W = 16 - 2 * _MARGIN     # 15.7
_FIT_H = 9 - 2 * _MARGIN      # 8.7

# font size for the finale numbers. Matches the 756 (built at 48 in three_rolls)
# and the cycle 8192, so nothing resizes when they move into the multiplication.
_GT_FS = 48
# font size for the captions that sit next to the finale numbers (Dice States,
# Box Combos, Board States, YAHTZEE Positions).
_LABEL_FS = 30


def _label(text):
    return crisp_text(text, font_size=_LABEL_FS, color=BLACK, font=FONT,
                      weight="BOLD")


def _fit_equal_margins(group):
    """Scale `group` to sit inside the equal-margin box (whichever dimension
    binds) and center it, so top/bottom margins match left/right."""
    group.scale_to_fit_width(_FIT_W)
    if group.height > _FIT_H:
        group.scale_to_fit_height(_FIT_H)
    group.move_to(ORIGIN)
    return group


def _balance_rows(group, rows):
    """After fitting, stretch the *row positions* (not the dice) so the grid
    fills _FIT_H, giving equal top/bottom and side margins. Only spreads rows
    apart vertically; each group keeps its size."""
    if rows < 2 or group.height >= _FIT_H - 1e-3:
        return group
    factor = _FIT_H / group.height
    cy = group.get_center()[1]
    for sub in group:
        x, y, z = sub.get_center()
        sub.move_to([x, cy + (y - cy) * factor, z])
    return group


class Intro(YahtzeeScene):
    """Scene 01 — the staggering number of Yahtzee positions.

    Follows the script's animation column beat-for-beat:
      one_die      — 6 dice outcomes (faces 1-6)
      all_outcomes — all 252 distinct 5-dice outcomes; then shrink the less likely
      three_rolls  — 3 rolls bottom->top, then 252 fanning out from each (756)
      box_combos   — blink the 13 card boxes, multiply 2's -> 8192
      one_card     — cycle filled scorecards -> 385,647,100,272
      grand_total  — count 385B down to 341,960,288,112, x756 -> 258,521,977,812,672
    """

    # LAZY BUILDING: each subscene builds what it OWNS by calling its
    # _setup_<name>() at its start; carry-over objects ride the snapshot. So
    # editing a late setup (e.g. _setup_grand_total) no longer rebuilds the heavy
    # build-up, and early snapshots stay light. See bpkfigures/CLAUDE.md.
    def setup_scene(self):
        pass

    def _setup_card(self):
        # ONE shared scorecard for the whole right-side / scorecard portion of
        # the scene (three_rolls -> box_combos -> one_card -> grand_total). Built
        # with scores=None so the 3rd (summary) column is empty. It fades in once
        # (in three_rolls) and persists — never refaded.
        self.card = get_scorecard(center=LEFT_SC, scores=None)

    # ── construction (all mobjects built/positioned here) ─────────────────────
    def _setup_one_die(self):
        SIZE = 1.5
        self.one_die_grid_size = SIZE
        self.one_die_lone_size = 2.6   # the big lone die before it splits out
        # The six single dice land in their k=1 build-up grid positions (3 rows
        # x 2 cols, column-major: 1,2,3 down the left column, 4,5,6 down the
        # right) so the build-up can grow straight out of them. The lone die
        # starts big at center; the six roll out shrinking to the grid size.
        # They roll in black; one_die recolors them once they land.
        targets = self._buildup_grid_centers(_multisets(1), SIZE,
                                              group_buff=0.04)
        self.one_die_targets = targets
        self.one_die_dice = [get_die(1, size=SIZE).move_to(ORIGIN)
                             for _ in range(6)]

    def _buildup_grid_centers(self, combos, die_size, group_buff):
        """Lay out one Die-group per combo (column-major, canonical order),
        fit to equal margins, and return the per-group center points. Used to
        derive target positions without keeping the throwaway layout group."""
        groups = VGroup(*[self._make_group(c, die_size, group_buff)
                          for c in combos])
        rows, cols = _GRID_SHAPE[len(combos)]
        groups.arrange_in_grid(rows=rows, cols=cols, buff=(group_buff * 4, group_buff * 4),
                               flow_order="dr")
        _fit_equal_margins(groups)
        _balance_rows(groups, rows)
        return [g.get_center() for g in groups]

    def _make_group(self, combo, die_size, buff):
        g = VGroup(*[get_die(v, size=die_size, pip_coloring=True) for v in combo])
        g.arrange(RIGHT, buff=buff)
        return g

    def _setup_buildup(self):
        # Per-step die sizes shrink as the groups grow so 252 still fits the
        # equal-margin box. k=1 matches one_die's SIZE so the dice grow out of
        # the landed singles.
        self.buildup_sizes = {1: 1.5, 2: 0.62, 3: 0.42, 4: 0.30, 5: 0.24}
        self.buildup_buff = {1: 0.04, 2: 0.04, 3: 0.035, 4: 0.03, 5: 0.025}

        # Build a grid (VGroup of Die-groups) for each k = 1..5 in canonical
        # column-major order, fit to equal margins. Index i in grid[k] matches
        # combos[k][i].
        self.combos = {k: _multisets(k) for k in range(1, 6)}
        self.bgrid = {}
        for k in range(1, 6):
            size, buff = self.buildup_sizes[k], self.buildup_buff[k]
            groups = VGroup(*[self._make_group(c, size, buff)
                              for c in self.combos[k]])
            rows, cols = _GRID_SHAPE[len(self.combos[k])]
            groups.arrange_in_grid(rows=rows, cols=cols,
                                   buff=(buff * 4, buff * 4), flow_order="dr")
            _fit_equal_margins(groups)
            _balance_rows(groups, rows)
            self.bgrid[k] = groups

        # k=1 grid IS the landed singles from one_die: drop the throwaway k=1
        # grid and reuse one_die's dice as grid[1] (already at those centers).
        self.bgrid[1] = VGroup(*[VGroup(d) for d in self.one_die_dice])

        # parent -> child index maps: child (canonical k+1 multiset) extends its
        # parent (first k of it) by appending x >= parent[-1]. parent index is
        # combos[k].index(child[:k]).
        self.child_of = {}
        for k in range(1, 5):
            idx_k = {c: i for i, c in enumerate(self.combos[k])}
            pairs = []  # (parent_i, child_i)
            for ci, child in enumerate(self.combos[k + 1]):
                pi = idx_k[child[:k]]
                pairs.append((pi, ci))
            self.child_of[k] = pairs

        # outcome shrink factors (likelihood) aligned to combos[5] order.
        # scale = sqrt(ways/120), so each group's AREA is proportional to how
        # many ways the outcome can occur (120 = a large straight -> 1.0).
        wmax = factorial(5)
        self.outcome_shrink = []
        for combo in self.combos[5]:
            vec = [combo.count(f) for f in range(1, 7)]
            ways = factorial(5)
            for c in vec:
                ways //= factorial(c)
            self.outcome_shrink.append((ways / wmax) ** 0.5)

    def _setup_three_rolls(self):
        # Gameplay layout (same as scene 99): scorecard left, 5 dice on the right
        # that roll UP through the four bands (BAND_YS), separated by the three
        # guide lines. The dice start in band 0 and roll up into 1, 2, 3. A "252"
        # is placed left of each roll; they knock down 252 -> 504 -> 756.
        self.tr_lines = roll_lines()

        # the single set of 5 dice, starting in band 0 (below the bottom line)
        start_vals = [2, 4, 6, 1, 3]
        self.tr_dice = [get_die(v).move_to(slot_point(0, s))
                        for s, v in enumerate(start_vals)]

        # the three rolls upward: band 1, 2, 3 (face values per roll)
        self.tr_roll_vals = [[4, 4, 6, 5, 3], [4, 4, 6, 6, 2], [3, 5, 6, 1, 4]]

        # count labels sit centered in the gap between the scorecard's right
        # edge and the leftmost die, at each roll's band height, in black.
        label_x = (self.card.get_right()[0] + (slot_x(0) - 0.5)) / 2
        self.tr_counts = [
            crisp_text("252", font_size=48, color=BLACK, font=FONT,
                       weight="BOLD").move_to([label_x, BAND_YS[b], 0])
            for b in (1, 2, 3)]
        self.tr_504 = crisp_text("504", font_size=48, color=BLACK, font=FONT,
                                 weight="BOLD").move_to([label_x, BAND_YS[2], 0])
        self.tr_756 = crisp_text("756", font_size=48, color=BLACK, font=FONT,
                                  weight="BOLD").move_to([label_x, BAND_YS[1], 0])
        # resting spot: centered under the dice (which stay up in band 3), just
        # below the dice row. Stays here through box_combos + the card cycle.
        self.tr_756_rest = [slot_x(2), BAND_YS[3] - 1.0, 0]
        # "Dice States" caption fades in below the 756 once it reaches rest.
        self.dice_states_label = _label("Dice States")
        self.dice_states_label.move_to([slot_x(2), BAND_YS[3] - 1.7, 0])

    def _setup_box_combos(self):
        # uses the shared self.card (built in _setup_card). The 2's / products
        # live in its empty 3rd (summary) column.
        cells = [self.card.value_cells[r] for r in range(13)]

        # per-row glow overlays: a newly-reached box lights BLUE for its first
        # two beats, then turns GREEN and stays lit. Build one of each per row.
        self.box_glow_blue = [
            c.copy().set_fill(ACCENT_FILL, opacity=0.65).set_stroke(width=0)
            for c in cells]
        self.box_glow_green = [
            c.copy().set_fill(SCORE_GREEN, opacity=0.65).set_stroke(width=0)
            for c in cells]

        # summary-column x (3rd column): centered between the value cells and the
        # card's right edge. The "2" for each row, and the running product the
        # row above bumps it into (2, 4, 8, ... 8192). All numbers black.
        # the real summary-column cell center (the value-cell/card-edge midpoint
        # is off because the rounded panel extends past the actual cells).
        summary_x = self._summary_column_x(cells[0])
        fs = 26

        def _num(s, y):
            return crisp_text(s, font_size=fs, color=BLACK, font=FONT,
                              weight="BOLD").move_to([summary_x, y, 0])

        self.box_twos = [_num("2", c.get_center()[1]) for c in cells]
        self.box_products = [_num(f"{2 ** (n + 1):,}", cells[n].get_center()[1])
                             for n in range(13)]

    def _summary_column_x(self, value_cell):
        """Center x of the scorecard's 3rd (summary) column — the tall summary
        rectangles sitting just right of the value column."""
        xs = [m.get_center()[0] for m in self.card.cells
              if isinstance(m, Rectangle)
              and m.get_center()[0] > value_cell.get_right()[0] + 0.05]
        return sum(xs) / len(xs) if xs else value_cell.get_right()[0] + 0.6

    def _setup_one_card(self):
        # ~12 valid complete scorecards the cycle_cards subscene flips through.
        fills = [_random_scorecard(seed) for seed in range(12)]
        self.card_fills = [get_scorecard(center=LEFT_SC, scores=f,
                                         show_summary=False)
                           for f in fills]
        # during the cycle the 8192 moves to the right of the MIDDLE of the
        # scorecard (same height as the card's center), with "Box Combos" below.
        card_mid_y = self.card.get_center()[1]
        self.cycle_8192 = crisp_text("8,192", font_size=_GT_FS, color=BLACK,
                                     font=FONT, weight="BOLD")
        self.cycle_8192.move_to([self.card.get_right()[0] + 1.6, card_mid_y, 0])
        self.box_combos_label = _label("Box Combos")
        self.box_combos_label.next_to(self.cycle_8192, DOWN, buff=0.35)

    def _setup_grand_total(self):
        # Finale value milestones (all black; counters are log-scale and built in
        # the subscene since their lambdas can't pickle):
        self.gt_positions   = 385_647_100_272      # 8192 counts up to this
        self.gt_after_cull  = 341_960_288_112      # tick down (remove finished)
        self.gt_final       = 258_521_977_812_672  # final (after x756 -> 1)
        self.gt_fs = _GT_FS
        # Centered multiplication: the big number is horizontally centered (x=0);
        # the two rows straddle the vertical center (top at +gap, bottom at -gap)
        # so the pair is vertically centered. The 756 row is right-aligned to the
        # big number's right edge.
        self.gt_top_y = 0.5        # big number row (above center)
        self.gt_bot_y = -0.5       # "x 756" row (below center)
        # during the multiply the big number grows and the 756 shrinks:
        self.gt_big_grow = 1.8
        self.gt_small_shrink = 0.5

    # ── helpers ───────────────────────────────────────────────────────────────
    def _recolor(self, die):
        """Animation turning a die's border + pips to its value color."""
        color = PIP_COLORS[die.value]
        return AnimationGroup(
            die.body.animate.set_stroke(color=color),
            *[dot.animate.set_color(color) for dot in die._pips.values()],
        )

    def _grow_step(self, k, run_time=2.4):
        """Grow grid[k] into grid[k+1].

        Each seed's first k dice are copies of the LIVE on-screen parent dice, so
        they start at exactly the parent's current size/position/color — no jump
        at the subscene boundary. Only the appended die comes from the child; it
        starts on the last parent die at opacity 0, so it fades in *while moving*
        (1114 -> 11144 in transit). The Transform then shrinks the whole group
        from the parent size down to the child size as it travels into the new
        grid. The parent grid is removed, so no originals linger."""
        src, dst = self.bgrid[k], self.bgrid[k + 1]

        seeds, transforms = [], []
        for parent_i, child_i in self.child_of[k]:
            parent = src[parent_i]          # VGroup of k dice, ON-SCREEN size
            child = dst[child_i]            # target: VGroup of k+1 dice
            seed_dice = [parent[j].copy() for j in range(k)]
            new_die = child[k].copy().move_to(parent[k - 1]).set_opacity(0.0)
            seed_dice.append(new_die)
            seed = VGroup(*seed_dice)
            seeds.append(seed)
            transforms.append(Transform(seed, child))

        self.add(*seeds)
        self.remove(src)                    # originals gone before the move
        self.play(LaggedStart(*transforms, lag_ratio=0.0006, run_time=run_time))
        # replace the seeds with the canonical dst grid for the next step
        self.remove(*seeds)
        self.add(dst)

    # ── 6 things can happen ───────────────────────────────────────────────────
    @subscene
    def one_die(self):
        self._setup_one_die()
        dice = self.one_die_dice
        big = self.one_die_lone_size
        grid = self.one_die_grid_size

        # one big die in the middle
        dice[0].scale(big / grid)
        self.play(FadeIn(dice[0]), run_time=1.0)
        self.wait(1)

        # the six roll out into the grid, each starting at the big lone size and
        # shrinking to the grid size as it tosses to its slot.
        for d in dice[1:]:
            d.move_to(ORIGIN)
            self.add(d)
        self.play(*[RollDie(d, t, v, start_size=big, end_size=grid)
                    for d, t, v in zip(dice, self.one_die_targets, range(1, 7))],
                  run_time=1.2)

        # as they land, the border + pips bloom from black into each value's
        # rainbow color (1 red ... 6 purple).
        self.play(LaggedStart(*[self._recolor(d) for d in dice],
                              lag_ratio=0.12, run_time=1.0))
        self.wait(1)

    # ── build up: 6 singles -> 21 pairs -> 56 trios -> 126 quads -> 252 quints ─
    @subscene
    def pairs(self):
        self._setup_buildup()           # owns the build-up grids (uses one_die_dice)
        self.add(self.bgrid[1])
        self._grow_step(1, run_time=2.4)
        self.wait(1)

    @subscene
    def trios(self):
        self._grow_step(2, run_time=2.4)
        self.wait(1)

    @subscene
    def quads(self):
        self._grow_step(3, run_time=2.4)
        self.wait(1)

    @subscene
    def quints(self):
        self._grow_step(4, run_time=2.4)
        self.wait(1)

    # ── shrink each of the 252 by how likely it is ────────────────────────────
    @subscene
    def shrink_outcomes(self):
        groups = self.bgrid[5]
        self.play(*[g.animate.scale(s)
                    for g, s in zip(groups, self.outcome_shrink)], run_time=1.5)
        self.wait(1)
        self.play(FadeOut(groups), run_time=1.0)

    # ── dice roll up through the bands, count 252 -> 504 -> 756 ───────────────
    @subscene
    def three_rolls(self):
        self._setup_card()              # owns the shared scorecard…
        self._setup_three_rolls()       # …and the roll dice / lines / counts
        dice = self.tr_dice

        # board + dice MOVE on screen (the lines just fade in): the card slides
        # in from the left, the dice rise up from below the screen into band 0.
        card_home = self.card.get_center()
        dice_homes = [d.get_center() for d in dice]
        self.card.shift(LEFT * 9)
        for d in dice:
            d.shift(DOWN * 7)
        self.add(self.card, *dice)
        self.play(
            self.card.animate.move_to(card_home),
            *[d.animate.move_to(h) for d, h in zip(dice, dice_homes)],
            FadeIn(self.tr_lines),
            run_time=0.9,
        )
        self.wait(0.35)      # brief beat before the first roll

        # the dice roll UP one band per roll (0->1->2->3). Each roll's "252"
        # fades in as it lands; the NEXT roll launches partway through that fade
        # (lag_ratio), so the rerolls start a little sooner.
        # roll and 252 keep their own run_times (0.9 / 0.3, same as before); the
        # next roll just LAUNCHES partway into the previous 252's fade (LaggedStart
        # with lag_ratio, no group run_time -> children aren't rescaled).
        def roll(band, vals, run_time=0.9):
            return AnimationGroup(*[RollDie(d, slot_point(band, s), v)
                                    for s, (d, v) in enumerate(zip(dice, vals))],
                                  run_time=run_time)

        def count_in(i, run_time=0.3):
            return FadeIn(self.tr_counts[i], shift=LEFT * 0.3, run_time=run_time)

        # roll_rt / count_rt are the per-roll knobs; reroll_lag controls how much
        # the next roll overlaps the previous 252's fade-in.
        roll_rt, count_rt, reroll_lag = 0.9, 0.3, 0.4
        self.play(roll(1, self.tr_roll_vals[0], run_time=roll_rt))
        for i, band in zip((1, 2), (2, 3)):
            self.play(LaggedStart(count_in(i - 1, run_time=count_rt),
                                  roll(band, self.tr_roll_vals[i], run_time=roll_rt),
                                  lag_ratio=reroll_lag))
        self.play(count_in(2, run_time=count_rt))
        self.wait(0.5)       # hold on the three 252s before they knock down

        # knock-downs: the upper number slides into the next one and snaps to the
        # sum the instant it arrives (instantaneous change, no morph).
        # 252(b3)+252(b2) -> 504 ; 504+252(b1) -> 756.
        top, mid, bot = self.tr_counts[2], self.tr_counts[1], self.tr_counts[0]
        self.play(top.animate.move_to(mid.get_center()), run_time=0.6)
        self.remove(top, mid)
        self.add(self.tr_504)
        self.play(self.tr_504.animate.move_to(bot.get_center()), run_time=0.6)
        self.remove(self.tr_504, bot)
        self.add(self.tr_756)

        # the lines fade out; the DICE STAY (up in band 3) and 756 moves to rest
        # just below them. Both persist through box_combos and the card cycle.
        self.play(
            self.tr_756.animate.move_to(self.tr_756_rest),
            FadeOut(self.tr_lines),
            run_time=1.0,
        )
        # "Dice States" fades in below the 756.
        self.play(FadeIn(self.dice_states_label, shift=UP * 0.2), run_time=0.5)
        self.wait(1)

    # ── flash the 13 boxes & multiply 2's down the 3rd column -> 8192 ──────────
    @subscene
    def box_combos(self):
        self._setup_box_combos()        # owns box glows / 2's / products (card carried)
        BEAT = 0.2
        N = 13
        twos, products = self.box_twos, self.box_products

        # the card is already on screen (persisted from three_rolls). The dice
        # there have faded; only the card + 756 corner remain.
        self.wait(0.4)

        # Beat timeline. Each box r lights BLUE on its appear beat (2r+1), stays
        # blue through its bump beat (2r+2), then turns GREEN and stays lit:
        #  - ODD beats (2r+1): row r's "2" appears, box r lights blue, and the
        #    previous box (r-1) converts blue -> green (it's had its 2 blue beats).
        #  - EVEN beats (2r+2), from beat 4: the running product slides onto row
        #    r's "2" and snaps to 2^(r+1) (same slide+snap as 252->504->756).
        blue, green = self.box_glow_blue, self.box_glow_green
        for g in blue + green:
            self.add(g); g.set_opacity(0.0)

        running = twos[0]                                # the first "2" = 2^1
        for r in range(N):
            # odd beat: new "2" + box r lights blue; prior box turns green
            anims = [FadeIn(twos[r], shift=UP * 0.15),
                     blue[r].animate.set_opacity(0.65)]
            if r >= 1:
                anims.append(blue[r - 1].animate.set_opacity(0.0))
                anims.append(green[r - 1].animate.set_opacity(0.65))
            self.play(*anims, run_time=BEAT)

            # even beat: bump (rows 1..N-1)
            if r >= 1:
                self.play(running.animate.move_to(products[r].get_center()),
                          run_time=BEAT)
                self.remove(running, twos[r])
                self.add(products[r])
                running = products[r]

        # the last box (r = N-1) is still blue; turn it green to finish the column
        self.play(blue[N - 1].animate.set_opacity(0.0),
                  green[N - 1].animate.set_opacity(0.65), run_time=BEAT)

        # hold on the final solid green column + 8192
        self.wait(1)
        # clear the green column but KEEP the 8192 (products[-1]) — it stays put
        # while the next subscene cycles through complete scorecards.
        self.play(*[g.animate.set_opacity(0.0) for g in green], run_time=0.4)

    # ── rapidly cycle complete scorecards (each ~0.2s, ~2s total) ─────────────
    @subscene
    def cycle_cards(self):
        self._setup_one_card()          # owns the filled cards (card / 8192 carried)
        sc = self.card        # empty card, on screen; dice/756 stay put
        fills = self.card_fills[:10]

        # The 8192 starts inside the card's 3rd column and slides out; the card
        # would otherwise occlude it. z_index is a PERSISTENT ordering that
        # survives the card-flip Transforms re-asserting their render order, so
        # the 8192 stays on top the whole way out. (The flipped card is a fresh
        # mobject each step; setting sc's z_index low keeps it behind.)
        sc.set_z_index(0)
        self.box_products[-1].set_z_index(10)
        self.cycle_8192.set_z_index(10)
        for f in self.card_fills:
            f.set_z_index(0)

        # Everything runs on ONE shared clock so nothing is sped up:
        #  - cards flip at a steady 0.2s the whole time (a Succession);
        #  - the 8192 moves out over 0.0-0.5s (its original 0.5s), then
        #  - "Box Combos" fades in over 0.5-0.9s (its original 0.4s) — i.e. the
        #    8192 and Box Combos stay SEQUENTIAL, exactly as before, just with
        #    the cards continuing to flip underneath instead of pausing.
        flips = Succession(*[Transform(sc, new, run_time=0.2) for new in fills])
        self.play(
            flips,                                                # 10 x 0.2s = 2.0s
            ReplacementTransform(self.box_products[-1], self.cycle_8192,
                                 run_time=0.5),                   # 0.0 - 0.5s
            Succession(Wait(0.5),
                       FadeIn(self.box_combos_label, shift=RIGHT * 0.2,
                              run_time=0.4)),                     # 0.5 - 0.9s
        )
        self.wait(0.6)

    # ── card/dice exit; 8192 -> 385B; cull; x756 down to 1 / count up to 258T ──
    @subscene
    def grand_total(self):
        self._setup_grand_total()       # owns gt_* (tr_dice / 8192 / card carried)
        import math
        dice = self.tr_dice
        fs = self.gt_fs

        # during the multiply (d) the big grows, the small shrinks, and the
        # captions fade out over the first ~1s (1/2.4 of _mult_t).
        self._mult_t = ValueTracker(0.0)
        big_scale = lambda: 1 + (self.gt_big_grow - 1) * self._mult_t.get_value()
        small_scale = lambda: 1 + (self.gt_small_shrink - 1) * self._mult_t.get_value()
        label_op = lambda: 1 - min(self._mult_t.get_value() / (1.0 / 2.4), 1.0)

        big_label = _label("Board States")
        small_label = _label("Dice States")

        def big_group(val, scale, y):
            """The big number (centered at x=0, height y, scaled) with its
            'Board States' caption to the right, scaled to match."""
            t = crisp_text(f"{int(round(val)):,}", font_size=fs, color=BLACK,
                           font=FONT, weight="BOLD").scale(scale)
            t.move_to([0, y, 0])
            lbl = big_label.copy().scale(scale).set_opacity(label_op())
            lbl.next_to(t, RIGHT, buff=0.4 * scale)
            return VGroup(t, lbl)

        # ── (a) 8192 log-counts up to 385B, ending as the centered top row.
        #        "Box Combos" crossfades to "Board States" as it transforms. ───
        big = ValueTracker(math.log10(8192))
        bigv = lambda: 10 ** big.get_value()
        start = self.cycle_8192.get_center()
        top_y = self.gt_top_y

        def big_frac():
            return _logfrac(bigv(), 8192, self.gt_positions)

        # while counting up the big number is at scale 1 and drifts to top_y.
        counter = always_redraw(lambda: big_group(bigv(), 1.0, 0)[0].move_to(
            _lerp(start, [0, top_y, 0], big_frac())))
        self.remove(self.cycle_8192)
        self.add(counter)

        # "Board States" tracks the big number and FADES IN (board_op: 0->1) as
        # "Box Combos" fades out — the crossfade during the count-up.
        board_op = ValueTracker(0.0)
        moving_big_label = always_redraw(lambda: big_label.copy()
                                         .next_to(counter, RIGHT, buff=0.4)
                                         .set_opacity(board_op.get_value()))
        self.add(moving_big_label)

        # card exits left, dice exit top, number counts up; "Box Combos" fades
        # OUT (first ~40%), then "Board States" fades IN (last ~40%) — sequential
        # with a gap, so the two captions are NEVER on screen at the same time.
        out_first = lambda t: smooth(min(t / 0.4, 1.0))        # done by 40%
        in_last = lambda t: smooth(max((t - 0.6) / 0.4, 0.0))  # starts at 60%
        self.play(
            self.card.animate.shift(LEFT * 9),
            *[d.animate.shift(UP * 7) for d in dice],
            big.animate.set_value(math.log10(self.gt_positions)),
            self.box_combos_label.animate(rate_func=out_first).set_opacity(0.0),
            board_op.animate(rate_func=in_last).set_value(1.0),
            run_time=2.2,
        )
        self.remove(self.box_combos_label)
        self.wait(0.1)

        # ── (b) 756 moves into the bottom row; "Dice States" moves to its right.
        small_log = ValueTracker(math.log10(756))
        smallv = lambda: 10 ** small_log.get_value()
        bot_y = self.gt_bot_y

        def bottom_group(scale):
            """'x <small>' right-aligned under the big number, + 'Dice States'
            caption to its right; everything scaled together."""
            big_right = big_group(bigv(), big_scale(), top_y)[0].get_right()[0]
            num_t = crisp_text(f"{int(round(smallv())):,}", font_size=fs,
                               color=BLACK, font=FONT, weight="BOLD").scale(scale)
            x_t = crisp_text("×", font_size=fs, color=BLACK, font=FONT,
                             weight="BOLD").scale(scale)
            num_t.move_to([big_right, bot_y, 0], aligned_edge=RIGHT)
            x_t.next_to(num_t, LEFT, buff=0.3 * scale)
            lbl = small_label.copy().scale(scale).set_opacity(label_op())
            lbl.next_to(num_t, RIGHT, buff=0.4 * scale)
            return VGroup(x_t, num_t, lbl)

        bottom = always_redraw(lambda: bottom_group(small_scale()))
        # slide the existing 756 into place + move Dice States to the 756's right
        self.tr_756.generate_target()
        self.tr_756.target.move_to(bottom_group(1.0)[1].get_center())
        self.dice_states_label.generate_target()
        self.dice_states_label.target.move_to(bottom_group(1.0)[2].get_center())
        self.play(MoveToTarget(self.tr_756),
                  MoveToTarget(self.dice_states_label), run_time=0.7)
        self.remove(self.tr_756, self.dice_states_label)
        self.add(bottom)
        self.wait(0.4)

        # rebuild the big counter+label so they scale and drift to center (y:
        # top_y->0) with _mult_t, landing centered as the 756 disappears.
        self.remove(counter, moving_big_label)
        big_counter = always_redraw(lambda: big_group(
            bigv(), big_scale(), top_y * (1 - self._mult_t.get_value())))
        self.add(big_counter)

        # ── (c) tick the top number down to remove finished states ────────────
        self.play(big.animate.set_value(math.log10(self.gt_after_cull)),
                  run_time=1.0)
        self.wait(0.4)

        # ── (d) multiply: big grows + counts up, small shrinks + counts down to
        #        1 (disappears); captions fade over the first ~1s. ─────────────
        self.play(
            big.animate.set_value(math.log10(self.gt_final)),
            small_log.animate.set_value(0),       # log10(1) = 0
            self._mult_t.animate.set_value(1.0),
            run_time=2.4,
        )
        # 756 reached 1 -> remove the bottom row; lock the final number centered.
        self.remove(big_counter, bottom)
        final = big_group(self.gt_final, self.gt_big_grow, 0)[0]
        self.add(final)

        # ── "YAHTZEE Positions" appears below the final number ────────────────
        positions_label = _label("YAHTZEE Positions").scale(1.3)
        positions_label.next_to(final, DOWN, buff=0.5)
        self.play(FadeIn(positions_label, shift=UP * 0.2), run_time=0.6)
        self.wait(1)
