"""
Turn-level transition kernel under the already-computed optimal policy.

For each reduced state row in a shard, compute the distribution over:

    category, reward, next_upper, next_eligible

after one full optimal turn.

This intentionally does NOT expose intermediate first-roll / keep / reroll
state. Most downstream forward/backward computations should only need this
compressed end-of-turn distribution.
"""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from constants import (
    NUM_CATEGORIES,
    SIXES,
    YAHTZEE,
    UPPER_BONUS,
    UPPER_BONUS_THRESHOLD,
    EXTRA_YAHTZEE_BONUS,
    YAHTZEE_POINTS,
    CATEGORY_NAMES,
)
from precomputed import (
    NUM_DICE_STATES,
    ALL_DICE_FREQS,
    REROLL_OUTCOMES,
    SCORE_ROWS,
    JOKER_SCORE_ROWS,
    IS_YAHTZEE_T,
)


DENOM = 7776 ** 3


@dataclass(frozen=True)
class TurnOutcome:
    category: int
    reward: int
    next_upper: int
    next_eligible: bool
    prob: float


def is_joker_roll(mask: int, dice_idx: int) -> bool:
    """A roll is a joker iff it is a Yahtzee and the Yahtzee box is already filled."""
    return bool(IS_YAHTZEE_T[dice_idx] and (mask & (1 << YAHTZEE)))


def immediate_transition(mask: int, upper: int, eligible: bool, dice_idx: int, category: int):
    """Return (reward, next_upper, next_eligible) for filling category with dice_idx.

    This mirrors ReducedGameState.fill_by_idx but avoids constructing objects.
    """
    is_joker = is_joker_roll(mask, dice_idx)

    if is_joker:
        points = JOKER_SCORE_ROWS[dice_idx][category]
    else:
        points = SCORE_ROWS[dice_idx][category]

    reward = int(points)

    if category <= SIXES:
        next_upper = min(int(upper) + int(points), UPPER_BONUS_THRESHOLD)
        if int(upper) < UPPER_BONUS_THRESHOLD and int(upper) + int(points) >= UPPER_BONUS_THRESHOLD:
            reward += UPPER_BONUS
    else:
        next_upper = int(upper)

    if is_joker and eligible:
        reward += EXTRA_YAHTZEE_BONUS

    if category == YAHTZEE and points == YAHTZEE_POINTS:
        next_eligible = True
    else:
        next_eligible = bool(eligible)

    return reward, next_upper, next_eligible


def row_turn_outcomes(mask: int, shard, row: int) -> list[TurnOutcome]:
    """Compressed one-turn outcome distribution for one row of one shard.

    Output is grouped by (category, reward, next_upper, next_eligible).
    Probabilities should sum to 1, up to floating-point roundoff.
    """
    upper = int(shard["upper_total"][row])
    eligible = bool(shard["yahtzee_eligible"][row])

    dec_A = shard["decisions_A"][row]
    dec_B = shard["decisions_B"][row]
    dec_C = shard["decisions_C"][row]

    numerators = defaultdict(int)

    # d0 = initial roll
    for d0 in range(NUM_DICE_STATES):
        n0 = int(ALL_DICE_FREQS[d0])
        kA = int(dec_A[d0])

        d1s, n1s = REROLL_OUTCOMES[(d0, kA)]

        # d1 = roll after first keep/reroll
        for d1, n1 in zip(d1s, n1s):
            d1 = int(d1)
            kB = int(dec_B[d1])

            d2s, n2s = REROLL_OUTCOMES[(d1, kB)]

            # d2 = final dice
            for d2, n2 in zip(d2s, n2s):
                d2 = int(d2)
                category = int(dec_C[d2])
                reward, next_upper, next_eligible = immediate_transition(
                    mask=mask,
                    upper=upper,
                    eligible=eligible,
                    dice_idx=d2,
                    category=category,
                )

                key = (category, reward, next_upper, next_eligible)
                numerators[key] += n0 * int(n1) * int(n2)

    return [
        TurnOutcome(
            category=category,
            reward=reward,
            next_upper=next_upper,
            next_eligible=next_eligible,
            prob=num / DENOM,
        )
        for (category, reward, next_upper, next_eligible), num in sorted(numerators.items())
    ]


def shard_turn_outcomes(mask: int, shard) -> list[list[TurnOutcome]]:
    """Return row_turn_outcomes(...) for every row in a shard."""
    N = shard["upper_total"].shape[0]
    return [row_turn_outcomes(mask, shard, row) for row in range(N)]


def print_row_turn_outcomes(mask: int, shard, row: int, min_prob: float = 0.0) -> None:
    """Debug display for one state row."""
    outcomes = row_turn_outcomes(mask, shard, row)
    total = sum(o.prob for o in outcomes)

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
            f"{CATEGORY_NAMES[o.category]:>10s}  "
            f"reward={o.reward:3d}  "
            f"next_upper={o.next_upper:2d}  "
            f"next_eligible={o.next_eligible}"
        )