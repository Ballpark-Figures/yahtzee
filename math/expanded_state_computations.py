from constants import NUM_CATEGORIES, YAHTZEE
from itertools import combinations
values_per_cell = [
    6, 6, 6, 6, 6, 6,
    27, 27, 2, 2, 2, 26, 2
]

# Case 3 (top not empty, but bottom not full)
# jokers with score 0 on top can't happen
joker_values_case3 = [
    1, 1, 1, 1, 1, 1,
    6, 6, 1, 1, 1, 6, 1
]

# Case 4 (top not empty, bottom is full)
# upper jokers can be 0 or 5 * face
joker_values_case4 = [
    2, 2, 2, 2, 2, 2,
    6, 6, 1, 1, 1, 6, 1
]

UPPER_MASK = (1 << 6) - 1
LOWER_MASK = ((1 << 7) - 1) << 6

def count_states_for_mask(filled_mask: int) -> int:
    yahtzee_filled = bool(filled_mask & (1 << YAHTZEE))
    top_empty = (filled_mask & UPPER_MASK) == 0
    bottom_full = (filled_mask & LOWER_MASK) == LOWER_MASK

    # Case 1: yahtzee not filled: num_yahtzees = 0
    if not yahtzee_filled:
        count = 1
        for c in range(NUM_CATEGORIES):
            if filled_mask & (1 << c):
                count *= values_per_cell[c]
        return count
    
    # Case 2: yahtzee filled, top empty.  num_yahtzees = 0 or 1
    if top_empty:
        count = 1
        for c in range(NUM_CATEGORIES):
            if filled_mask & (1 << c):
                count *= values_per_cell[c]
        return count
    
    # Cases 3 and 4: yahtzee filled, top non-empty
    joker_values = joker_values_case4 if bottom_full else joker_values_case3

    non_yahtzee_filled = [
        c for c in range(NUM_CATEGORIES)
        if c != YAHTZEE and (filled_mask & (1 << c))
    ]

    P = 1
    for c in non_yahtzee_filled:
        P *= values_per_cell[c]

    # 0 or 1 yahtzee
    count = 2 * P

    # 2+ yahtzees: for each nonempty subset of non-yahtzee filled cells
    # take product of joker values in subset, times non-joker values out of subset, times size of subset
    for size in range(1, len(non_yahtzee_filled) + 1):
        for S in combinations(non_yahtzee_filled, size):
            S_set = set(S)
            contribution = size
            for c in non_yahtzee_filled:
                if c in S_set:
                    contribution *= joker_values[c]
                else:
                    contribution *= values_per_cell[c] - joker_values[c]
            count += contribution
    return count

def count_expanded_states_per_level() -> list[int]:
    counts = [0] * (NUM_CATEGORIES + 1)
    for filled_mask in range(1 << NUM_CATEGORIES):
        level = filled_mask.bit_count()
        counts[level] += count_states_for_mask(filled_mask)
    return counts


if __name__ == "__main__":
    counts = count_expanded_states_per_level()
    total = sum(counts)
    for level, count in enumerate(counts):
        print(f"level {level:2d}: {count:>18,}")
    print(f"total:    {total:>18,}")