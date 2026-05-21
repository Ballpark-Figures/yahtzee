"""
Turn-level transition kernel under the already-computed optimal policy.

For one reduced state row in one value-iteration shard, compute the compressed
distribution over end-of-turn outcomes:

    (category, box_points, reward, next_upper, next_eligible)

where:

    category      = box filled at the end of the turn
    box_points    = points written in that box, excluding bonuses
    reward        = immediate reduced reward:
                    box_points
                    + upper bonus if crossed this turn
                    + extra Yahtzee bonus if earned this turn
    next_upper    = capped upper total after the turn
    next_eligible = whether future extra-Yahtzee bonuses are enabled

The saved turn-kernel files use a CSR-like layout:
    offsets[row] : offsets[row + 1] gives the outcome slice for that row.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from constants import (
    CATEGORY_NAMES,
    SIXES,
    YAHTZEE,
    UPPER_BONUS,
    UPPER_BONUS_THRESHOLD,
    EXTRA_YAHTZEE_BONUS,
    YAHTZEE_POINTS,
)
from precomputed import (
    NUM_DICE_STATES,
    ALL_DICE_FREQS,
    REROLL_OUTCOMES,
    SCORE_ROWS,
    JOKER_SCORE_ROWS,
    IS_YAHTZEE_T,
)


TURN_KERNEL_DIR = "data/turn_kernels"

# All probability numerators are represented out of 7776.
# A full turn consists of:
#   initial roll numerator * first-reroll numerator * second-reroll numerator
DENOM = 7776 ** 3


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    category: int
    box_points: int
    reward: int
    next_upper: int
    next_eligible: bool
    numerator: int

    @property
    def prob(self) -> float:
        return self.numerator / DENOM

    @property
    def next_eligible_idx(self) -> int:
        return int(self.next_eligible)

    @property
    def category_name(self) -> str:
        return CATEGORY_NAMES[self.category]


def turn_kernel_path(level: int, mask: int) -> str:
    return os.path.join(TURN_KERNEL_DIR, f"level_{level:02d}", f"{mask:013b}.npz")


def next_mask_from_outcome(mask: int, outcome: TurnOutcome) -> int:
    return mask | (1 << outcome.category)


def is_joker_roll(mask: int, dice_idx: int) -> bool:
    """A roll is a joker iff it is a Yahtzee and the Yahtzee box is filled."""
    return bool(IS_YAHTZEE_T[dice_idx] and (mask & (1 << YAHTZEE)))


def immediate_transition(
    *,
    mask: int,
    upper: int,
    eligible: bool,
    dice_idx: int,
    category: int,
) -> tuple[int, int, int, bool]:
    """Return (box_points, reward, next_upper, next_eligible).

    This mirrors ReducedGameState.fill_by_idx, but avoids constructing a
    ReducedGameState object for each final dice/category outcome.
    """
    is_joker = is_joker_roll(mask, dice_idx)

    if is_joker:
        box_points = int(JOKER_SCORE_ROWS[dice_idx][category])
    else:
        box_points = int(SCORE_ROWS[dice_idx][category])

    reward = box_points

    if category <= SIXES:
        old_upper = int(upper)
        uncapped_upper = old_upper + box_points
        next_upper = min(uncapped_upper, UPPER_BONUS_THRESHOLD)

        if old_upper < UPPER_BONUS_THRESHOLD and uncapped_upper >= UPPER_BONUS_THRESHOLD:
            reward += UPPER_BONUS
    else:
        next_upper = int(upper)

    if is_joker and eligible:
        reward += EXTRA_YAHTZEE_BONUS

    if category == YAHTZEE and box_points == YAHTZEE_POINTS:
        next_eligible = True
    else:
        next_eligible = bool(eligible)

    return box_points, reward, next_upper, next_eligible


def row_turn_outcomes(mask: int, shard, row: int) -> list[TurnOutcome]:
    """Return grouped one-turn outcomes for one row of one shard.

    The grouping key is:

        (category, box_points, reward, next_upper, next_eligible)

    Probabilities should sum to 1, up to floating-point roundoff.
    """
    upper = int(shard["upper_total"][row])
    eligible = bool(shard["yahtzee_eligible"][row])

    dec_A = shard["decisions_A"][row]
    dec_B = shard["decisions_B"][row]
    dec_C = shard["decisions_C"][row]

    numerators: dict[tuple[int, int, int, int, bool], int] = defaultdict(int)

    # d0: initial roll.
    for d0 in range(NUM_DICE_STATES):
        n0 = int(ALL_DICE_FREQS[d0])
        keep_A = int(dec_A[d0])

        d1s, n1s = REROLL_OUTCOMES[(d0, keep_A)]

        # d1: dice after first keep/reroll.
        for d1, n1 in zip(d1s, n1s):
            d1 = int(d1)
            keep_B = int(dec_B[d1])

            d2s, n2s = REROLL_OUTCOMES[(d1, keep_B)]

            # d2: final dice after second keep/reroll.
            for d2, n2 in zip(d2s, n2s):
                d2 = int(d2)
                category = int(dec_C[d2])

                box_points, reward, next_upper, next_eligible = immediate_transition(
                    mask=mask,
                    upper=upper,
                    eligible=eligible,
                    dice_idx=d2,
                    category=category,
                )

                key = (category, box_points, reward, next_upper, next_eligible)
                numerators[key] += n0 * int(n1) * int(n2)

    outcomes = [
        TurnOutcome(
            category=category,
            box_points=box_points,
            reward=reward,
            next_upper=next_upper,
            next_eligible=next_eligible,
            numerator=numerator,
        )
        for (category, box_points, reward, next_upper, next_eligible), numerator
        in numerators.items()
    ]

    outcomes.sort(
        key=lambda o: (
            o.category,
            o.box_points,
            o.reward,
            o.next_upper,
            o.next_eligible,
        )
    )
    return outcomes


def shard_turn_outcomes(mask: int, shard) -> list[list[TurnOutcome]]:
    """Return row_turn_outcomes(...) for every row in a shard."""
    n_rows = shard["upper_total"].shape[0]
    return [row_turn_outcomes(mask, shard, row) for row in range(n_rows)]


def outcomes_to_arrays(outcomes_by_row: list[list[TurnOutcome]]) -> dict[str, np.ndarray]:
    """Convert variable-length per-row outcomes into flat CSR-style arrays."""
    n_rows = len(outcomes_by_row)
    lengths = np.array([len(outcomes) for outcomes in outcomes_by_row], dtype=np.int64)

    offsets = np.empty(n_rows + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(lengths, out=offsets[1:])

    total = int(offsets[-1])

    category = np.empty(total, dtype=np.uint8)
    box_points = np.empty(total, dtype=np.int16)
    reward = np.empty(total, dtype=np.int16)
    next_upper = np.empty(total, dtype=np.uint8)
    next_eligible = np.empty(total, dtype=bool)
    numerator = np.empty(total, dtype=np.int64)

    pos = 0
    for outcomes in outcomes_by_row:
        for o in outcomes:
            category[pos] = o.category
            box_points[pos] = o.box_points
            reward[pos] = o.reward
            next_upper[pos] = o.next_upper
            next_eligible[pos] = o.next_eligible
            numerator[pos] = o.numerator
            pos += 1

    return {
        "offsets": offsets,
        "category": category,
        "box_points": box_points,
        "reward": reward,
        "next_upper": next_upper,
        "next_eligible": next_eligible,
        "numerator": numerator,
        "denom": np.array(DENOM, dtype=np.int64),
    }


def save_turn_kernel(level: int, mask: int, arrays: dict[str, np.ndarray]) -> None:
    path = turn_kernel_path(level, mask)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)


def load_turn_kernel(level: int, mask: int) -> np.lib.npyio.NpzFile:
    path = turn_kernel_path(level, mask)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing turn kernel: {path}")
    return np.load(path)


def row_slice(kernel, row: int) -> slice:
    start = int(kernel["offsets"][row])
    end = int(kernel["offsets"][row + 1])
    return slice(start, end)


def probability_sum(outcomes: Iterable[TurnOutcome]) -> float:
    return sum(o.prob for o in outcomes)


def expected_immediate_reward(outcomes: Iterable[TurnOutcome]) -> float:
    return sum(o.prob * o.reward for o in outcomes)


def print_row_turn_outcomes(
    mask: int,
    shard,
    row: int,
    *,
    min_prob: float = 0.0,
) -> None:
    """Debug display for one state row."""
    outcomes = row_turn_outcomes(mask, shard, row)
    total = probability_sum(outcomes)

    upper = int(shard["upper_total"][row])
    eligible = bool(shard["yahtzee_eligible"][row])

    print(f"mask={mask:013b}, row={row}, upper={upper}, eligible={eligible}")
    print(f"{len(outcomes)} grouped outcomes; total probability = {total:.12f}")
    print()

    for o in outcomes:
        if o.prob < min_prob:
            continue

        print(
            f"{o.prob: .8f}  "
            f"{o.category_name:>10s}  "
            f"box={o.box_points:3d}  "
            f"reward={o.reward:3d}  "
            f"next_upper={o.next_upper:2d}  "
            f"next_eligible={o.next_eligible}"
        )