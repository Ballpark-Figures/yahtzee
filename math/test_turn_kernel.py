import numpy as np

from constants import UPPER_BONUS_THRESHOLD
from state_properties import load_shard, row_index
from turn_kernel import row_turn_outcomes


def load_v_table(level, mask):
    with load_shard(level, mask) as shard:
        table = np.zeros((UPPER_BONUS_THRESHOLD + 1, 2), dtype=np.float64)
        table[
            shard["upper_total"],
            shard["yahtzee_eligible"].astype(np.int8),
        ] = shard["V"]
    return table


def check_value_reconstruction(level, mask, upper, eligible):
    with load_shard(level, mask) as shard:
        row = row_index(shard, upper, eligible)
        outcomes = row_turn_outcomes(mask, shard, row)

        next_v_cache = {}
        reconstructed = 0.0

        for o in outcomes:
            next_mask = mask | (1 << o.category)

            if next_mask not in next_v_cache:
                next_v_cache[next_mask] = load_v_table(level + 1, next_mask)

            next_v = next_v_cache[next_mask]
            reconstructed += o.prob * (
                o.reward + next_v[o.next_upper, int(o.next_eligible)]
            )

        stored = float(shard["V"][row])
        print("stored V:       ", stored)
        print("reconstructed V:", reconstructed)
        print("difference:     ", reconstructed - stored)


if __name__ == "__main__":
    check_value_reconstruction(level=0, mask=0, upper=0, eligible=False)