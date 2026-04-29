import numpy as np

ONES, TWOS, THREES, FOURS, FIVES, SIXES = range(6)
THREE_KIND = 6
FOUR_KIND = 7
FULL_HOUSE = 8
SMALL_STRAIGHT = 9
LARGE_STRAIGHT = 10
CHANCE = 11
YAHTZEE = 12

FULL_HOUSE_POINTS = 25
SMALL_STRAIGHT_POINTS = 30
LARGE_STRAIGHT_POINTS = 40
YAHTZEE_POINTS = 50

def get_sum(dice_vec):
    return np.dot(dice_vec, np.arange(1, 7))

def single_num_points(dice_vec, num):
    return num * dice_vec[num - 1]

def three_kind_points(dice_vec):
    return get_sum(dice_vec) * (dice_vec.max() >= 3)

def four_kind_points(dice_vec):
    return get_sum(dice_vec) * (dice_vec.max() >= 4)

def full_house_points(dice_vec):
    return FULL_HOUSE_POINTS * (((3 in dice_vec) and (2 in dice_vec)) or (5 in dice_vec))

def small_straight_points(dice_vec):
    return SMALL_STRAIGHT_POINTS * (np.prod(dice_vec[0:4]) + np.prod(dice_vec[1:5]) + np.prod(dice_vec[2:6]) > 0)

def large_straight_points(dice_vec):
    return LARGE_STRAIGHT_POINTS * (np.prod(dice_vec[0:5]) + np.prod(dice_vec[1:6]) > 0)

def chance_points(dice_vec):
    return get_sum(dice_vec)

def yahtzee_points(dice_vec):
    return YAHTZEE_POINTS * (5 in dice_vec)

SCORING_FUNCTIONS = [
    lambda x, i=i: single_num_points(x, i) for i in range(1, 7)
] + [
    three_kind_points,
    four_kind_points,
    full_house_points,
    small_straight_points,
    large_straight_points,
    chance_points,
    yahtzee_points
]

def joker_points(dice_vec, scoring_function_index):
    if scoring_function_index == SMALL_STRAIGHT:
        return SMALL_STRAIGHT_POINTS
    elif scoring_function_index == LARGE_STRAIGHT:
        return LARGE_STRAIGHT_POINTS
    else:
        return SCORING_FUNCTIONS[scoring_function_index](dice_vec)