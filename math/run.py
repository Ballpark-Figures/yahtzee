"""Compute all six per-state properties on top of the value-iteration policy.

Usage from project root:
    python -m computations.run

To compute a subset, edit the lists below or call run_backward / run_forward
directly with the functionals you want.

The backward and forward passes are independent; you can run them in any
order. Each pass adds named arrays to the existing shards at
data/state_properties/level_kk/<mask>.npz via save_shard(..., merge=True).
"""
from .framework import run_backward, run_forward
from .properties import (
    ExpectedScoreAfter, ScoreDistAfter, BoxDistAfter, PTopBonusAfter,
    ScoreDistBefore, BoxDistBefore,
)


BACKWARD = [
    ExpectedScoreAfter(),
    ScoreDistAfter(),
    BoxDistAfter(),
    PTopBonusAfter(),
]

FORWARD = [
    ScoreDistBefore(),
    BoxDistBefore(),
]


def main():
    print("=== Backward pass ===")
    run_backward(BACKWARD)
    print()
    print("=== Forward pass ===")
    run_forward(FORWARD)
    print()
    print("Done. New arrays available in data/state_properties/.")


if __name__ == "__main__":
    main()