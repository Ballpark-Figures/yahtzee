import numpy as np

from state_properties import load_shard, row_index
from turn_kernel import row_turn_outcomes, print_row_turn_outcomes


def check_state(level, mask, upper, eligible):
    with load_shard(level, mask) as shard:
        row = row_index(shard, upper, eligible)

        outcomes = row_turn_outcomes(mask, shard, row)
        p = sum(o.prob for o in outcomes)
        ev = sum(o.prob * o.reward for o in outcomes)

        print_row_turn_outcomes(mask, shard, row, min_prob=0.001)
        print()
        print("probability sum:", p)
        print("one-turn expected immediate reward:", ev)
        print("stored V:", float(shard["V"][row]))


if __name__ == "__main__":
    check_state(level=0, mask=0, upper=0, eligible=False)