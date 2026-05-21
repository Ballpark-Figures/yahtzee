"""I/O for per-state properties stored as sharded .npz files.

Each shard at data/state_properties/level_kk/<13-bit mask>.npz holds the
arrays for all reduced states sharing that (level, mask). Rows within a
shard are sorted by (upper_total, yahtzee_eligible) -- this convention is
established by value_iteration.process_mask and assumed by readers.

Standard arrays written by value iteration:
    upper_total       : (N,)         uint8
    yahtzee_eligible  : (N,)         bool
    V                 : (N,)         float32
    decisions_A       : (N, 252)     uint16  optimal keep idx, stage A
    decisions_B       : (N, 252)     uint16  optimal keep idx, stage B
    decisions_C       : (N, 252)     uint8   optimal category, stage C
    ev_A              : (N, 252)     float32 EV given roll, stage A
    ev_B              : (N, 252)     float32 EV given roll, stage B
    ev_C              : (N, 252)     float32 EV given roll, stage C

Future per-state functionals (score distributions, bonus probabilities, ...)
get added as additional named arrays in the same shard.
"""
import os
import numpy as np


STATE_PROPERTIES_DIR = "data/state_properties"


def shard_path(level: int, mask: int) -> str:
    return os.path.join(STATE_PROPERTIES_DIR, f"level_{level:02d}", f"{mask:013b}.npz")


def load_shard(level: int, mask: int) -> np.lib.npyio.NpzFile:
    """Return the npz archive for (level, mask).

    Arrays inside are loaded lazily on attribute access; close with `.close()`
    or use as a context manager when reading many of them.
    """
    path = shard_path(level, mask)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing shard: {path}")
    return np.load(path)


def save_shard(level: int, mask: int, *, merge: bool = True, **arrays) -> None:
    """Write `arrays` to the shard for (level, mask), atomically.

    If `merge` is True (default), existing arrays in the shard whose names
    are not in `arrays` are preserved; existing arrays whose names ARE in
    `arrays` get overwritten. If False, the shard is rewritten from scratch
    with only the supplied arrays.
    """
    path = shard_path(level, mask)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if merge and os.path.exists(path):
        with np.load(path) as existing:
            merged = {name: existing[name] for name in existing.files}
        merged.update(arrays)
    else:
        merged = dict(arrays)

    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, **merged)
    os.replace(tmp, path)


def row_index(shard, upper_total: int, yahtzee_eligible: bool) -> int:
    """Find the row in `shard` matching (upper_total, yahtzee_eligible)."""
    matches = np.where(
        (shard["upper_total"] == upper_total) &
        (shard["yahtzee_eligible"] == bool(yahtzee_eligible))
    )[0]
    if len(matches) == 0:
        raise KeyError(
            f"State (upper={upper_total}, eligible={yahtzee_eligible}) "
            "not found in shard"
        )
    return int(matches[0])