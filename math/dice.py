import numpy as np
import pickle

def vec_key(vec):
    return tuple(map(int, vec))

def dice_values_to_vec(vals, sides=6):
    vals = np.asarray(vals, dtype=int)
    return np.bincount(vals, minlength=sides + 1)[1:sides + 1]

def all_rolls(n_dice=5, sides=6):
    if n_dice == 0:
        return np.empty((1, 0), dtype=int)
    
    return np.indices((sides,) * n_dice).reshape(n_dice, -1).T + 1

def dice_state_freqs(n_dice=5, sides=6):
    rolls = all_rolls(n_dice=n_dice, sides=sides)
    dice_states = np.array(
        [dice_values_to_vec(roll, sides=sides) for roll in rolls],
        dtype=int,
    )
    return np.unique(dice_states, axis=0, return_counts=True)


def get_all_sub_vecs(dice_state):
    dice_state = np.asarray(dice_state, dtype=int)
    grids = np.indices(tuple(dice_state + 1))
    return grids.reshape(len(dice_state), -1).T

def get_sub_vecs_for_all(n_dice=5, sides=6):
    dice_states, _ = dice_state_freqs(n_dice=n_dice, sides=sides)

    return {
        vec_key(dice_state): get_all_sub_vecs(dice_state)
        for dice_state in dice_states
    }

def get_reroll_results(keep_vec, total_dice=5, sides=6):
    keep_vec = np.asarray(keep_vec, dtype=int)

    if len(keep_vec) != sides:
        raise ValueError(f"keep_vec has length {len(keep_vec)}, expected {sides}")

    n_reroll = total_dice - int(keep_vec.sum())

    if n_reroll < 0:
        raise ValueError("keep_vec contains more dice than total_dice")

    reroll_vecs, freqs = dice_state_freqs(n_dice=n_reroll, sides=sides)
    final_vecs = reroll_vecs + keep_vec

    return final_vecs, freqs


def get_all_reroll_results(dice_state, total_dice=5, sides=6):
    dice_state = np.asarray(dice_state, dtype=int)

    if len(dice_state) != sides:
        raise ValueError(f"dice_state has length {len(dice_state)}, expected {sides}")

    return {
        vec_key(keep_vec): get_reroll_results(
            keep_vec,
            total_dice=total_dice,
            sides=sides,
        )
        for keep_vec in get_all_sub_vecs(dice_state)
    }


def get_reroll_results_for_all(n_dice=5, sides=6):
    dice_states, _ = dice_state_freqs(n_dice=n_dice, sides=sides)

    return {
        vec_key(dice_state): get_all_reroll_results(
            dice_state,
            total_dice=n_dice,
            sides=sides,
        )
        for dice_state in dice_states
    }