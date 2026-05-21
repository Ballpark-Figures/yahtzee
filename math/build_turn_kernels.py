"""
Generate simplified one-turn transition files from value-iteration shards.

Input:
    data/state_properties/level_kk/<mask>.npz

Output:
    data/turn_kernels/level_kk/<mask>.npz

Each output file stores a CSR-style grouped distribution over:

    category, box_points, reward, next_upper, next_eligible

for every row in the corresponding state_properties shard.

Run from project root:

    python build_turn_kernels.py

Useful options:

    python build_turn_kernels.py --workers 8
    python build_turn_kernels.py --workers 1
    python build_turn_kernels.py --start-level 0 --end-level 3
    python build_turn_kernels.py --force
"""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from tqdm import tqdm

from state_properties import STATE_PROPERTIES_DIR, load_shard
from turn_kernel import (
    turn_kernel_path,
    shard_turn_outcomes,
    outcomes_to_arrays,
    save_turn_kernel,
)


REQUIRED_ARRAYS = (
    "upper_total",
    "yahtzee_eligible",
    "decisions_A",
    "decisions_B",
    "decisions_C",
)


def list_masks_for_level(level: int) -> list[int]:
    level_dir = os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}")
    if not os.path.isdir(level_dir):
        return []

    masks = []
    for filename in os.listdir(level_dir):
        if filename.endswith(".npz"):
            masks.append(int(filename[:-4], 2))

    return sorted(masks)


def load_policy_shard(level: int, mask: int) -> dict:
    """Load only the arrays needed to build the turn kernel.

    This avoids repeatedly asking an NpzFile to decompress arrays inside the
    per-row loop.
    """
    with load_shard(level, mask) as shard:
        return {name: shard[name] for name in REQUIRED_ARRAYS}


def build_one(level: int, mask: int, *, force: bool = False) -> tuple[int, int, int, int, str]:
    """Build one kernel shard.

    Returns:
        (level, mask, n_rows, n_outcomes, status)
    """
    out_path = turn_kernel_path(level, mask)

    if os.path.exists(out_path) and not force:
        with load_shard(level, mask) as shard:
            n_rows = int(shard["upper_total"].shape[0])
        return level, mask, n_rows, -1, "skipped"

    shard = load_policy_shard(level, mask)
    outcomes_by_row = shard_turn_outcomes(mask, shard)
    arrays = outcomes_to_arrays(outcomes_by_row)
    save_turn_kernel(level, mask, arrays)

    n_rows = len(outcomes_by_row)
    n_outcomes = int(arrays["offsets"][-1])
    return level, mask, n_rows, n_outcomes, "written"


def build_level(level: int, *, workers: int | None, force: bool) -> None:
    if workers is None:
        workers = os.cpu_count()

    masks = list_masks_for_level(level)

    if not masks:
        print(f"level {level:2d}: no state_properties shards found")
        return

    print(f"level {level:2d}: {len(masks):,} masks, workers={workers}")

    if workers <= 1:
        total_rows = 0
        total_outcomes = 0
        written = 0
        skipped = 0

        for mask in tqdm(masks, desc=f"turn kernels L{level:02d}"):
            _, _, n_rows, n_outcomes, status = build_one(level, mask, force=force)
            total_rows += n_rows

            if status == "written":
                written += 1
                total_outcomes += n_outcomes
            else:
                skipped += 1

        print(
            f"level {level:2d}: written={written:,}, skipped={skipped:,}, "
            f"rows={total_rows:,}, outcomes={total_outcomes:,}"
        )
        return

    total_rows = 0
    total_outcomes = 0
    written = 0
    skipped = 0

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(build_one, level, mask, force=force)
            for mask in masks
        ]

        for future in tqdm(as_completed(futures), total=len(futures), desc=f"turn kernels L{level:02d}"):
            _, _, n_rows, n_outcomes, status = future.result()
            total_rows += n_rows

            if status == "written":
                written += 1
                total_outcomes += n_outcomes
            else:
                skipped += 1

    print(
        f"level {level:2d}: written={written:,}, skipped={skipped:,}, "
        f"rows={total_rows:,}, outcomes={total_outcomes:,}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-level", type=int, default=0)
    parser.add_argument("--end-level", type=int, default=12)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    for level in range(args.start_level, args.end_level + 1):
        build_level(level, workers=args.workers, force=args.force)


if __name__ == "__main__":
    main()