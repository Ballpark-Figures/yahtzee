"""
Validate per-box score distributions.

Currently validates backward/after distributions:

    box_score_dist_after_00
    ...
    box_score_dist_after_12

Run:

    python validate_box_distributions.py backward-after --category FullHouse
    python validate_box_distributions.py backward-after --all
"""

from __future__ import annotations

import argparse
import os

import numpy as np

from constants import NUM_CATEGORIES, CATEGORY_NAMES
from state_properties import STATE_PROPERTIES_DIR, load_shard


MAX_BOX_POINTS = 50
N_BOX_BINS = MAX_BOX_POINTS + 1


def box_after_name(category: int) -> str:
    return f"box_score_dist_after_{category:02d}"


def category_from_arg(arg: str) -> int:
    try:
        c = int(arg)
    except ValueError:
        if arg not in CATEGORY_NAMES:
            raise ValueError(
                f"Unknown category {arg!r}. Use 0..12 or one of {CATEGORY_NAMES}."
            )
        c = CATEGORY_NAMES.index(arg)

    if not 0 <= c < NUM_CATEGORIES:
        raise ValueError(f"Category must be in 0..{NUM_CATEGORIES - 1}; got {c}")

    return c


def list_masks_for_level(level: int) -> list[int]:
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []

    masks = []
    for filename in os.listdir(level_dir):
        if filename.endswith(".npz"):
            masks.append(int(filename[:-4], 2))

    return sorted(masks)


def validate_backward_after_category(category: int) -> None:
    name = box_after_name(category)

    worst_unfilled_mass_error = 0.0
    worst_filled_mass = 0.0
    checked_unfilled = 0
    checked_filled = 0
    initial_dist = None

    for level in range(NUM_CATEGORIES + 1):
        total_unfilled_mass = 0.0
        n_unfilled_rows = 0
        total_filled_mass = 0.0
        n_filled_rows = 0

        for mask in list_masks_for_level(level):
            with load_shard(level, mask) as shard:
                if name not in shard.files:
                    raise KeyError(
                        f"Missing {name} in level={level}, mask={mask:013b}"
                    )
                dist = shard[name].astype(np.float64)

            row_mass = dist.sum(axis=1)

            if mask & (1 << category):
                if len(row_mass):
                    max_mass = float(np.max(np.abs(row_mass)))
                    worst_filled_mass = max(worst_filled_mass, max_mass)
                    total_filled_mass += float(row_mass.sum())
                    n_filled_rows += len(row_mass)
                    checked_filled += len(row_mass)
            else:
                if len(row_mass):
                    err = float(np.max(np.abs(row_mass - 1.0)))
                    worst_unfilled_mass_error = max(worst_unfilled_mass_error, err)
                    total_unfilled_mass += float(row_mass.sum())
                    n_unfilled_rows += len(row_mass)
                    checked_unfilled += len(row_mass)

            if level == 0 and mask == 0:
                initial_dist = dist[0].copy()

        avg_unfilled_mass = (
            total_unfilled_mass / n_unfilled_rows if n_unfilled_rows else np.nan
        )
        avg_filled_mass = (
            total_filled_mass / n_filled_rows if n_filled_rows else np.nan
        )

        print(
            f"level {level:2d}: "
            f"unfilled rows={n_unfilled_rows:7,d}, "
            f"avg unfilled mass={avg_unfilled_mass:.12f}, "
            f"filled rows={n_filled_rows:7,d}, "
            f"avg filled mass={avg_filled_mass:.12f}"
        )

    scores = np.arange(N_BOX_BINS, dtype=np.float64)

    print()
    print(f"category: {category} {CATEGORY_NAMES[category]}")
    print(f"checked unfilled rows:       {checked_unfilled:,}")
    print(f"checked filled rows:         {checked_filled:,}")
    print(f"worst unfilled mass error:   {worst_unfilled_mass_error:.12g}")
    print(f"worst filled mass:           {worst_filled_mass:.12g}")

    if initial_dist is not None:
        nonzero = np.where(initial_dist > 1e-8)[0]
        print()
        print("initial distribution:")
        print(f"  mass: {initial_dist.sum():.12f}")
        print(f"  mean: {float(initial_dist @ scores):.12f}")
        print("  nonzero:")
        for x in nonzero:
            print(f"    {x:2d}: {initial_dist[x]:.12f}")

    if worst_unfilled_mass_error > 1e-4:
        raise SystemExit("Unfilled-row mass error too large.")

    if worst_filled_mass > 1e-8:
        raise SystemExit("Filled-row mass should be zero.")

    print()
    print("validation passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("backward-after")
    p.add_argument("--category", type=str, default=None)
    p.add_argument("--all", action="store_true")

    args = parser.parse_args()

    if args.command == "backward-after":
        if args.all:
            categories = list(range(NUM_CATEGORIES))
        elif args.category is not None:
            categories = [category_from_arg(args.category)]
        else:
            raise SystemExit("Pass --category <0..12/name> or --all.")

        for category in categories:
            print("=" * 80)
            validate_backward_after_category(category)


if __name__ == "__main__":
    main()