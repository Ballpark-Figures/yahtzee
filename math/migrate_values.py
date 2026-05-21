"""One-time migration from data/values/*.pkl to data/state_properties/*.npz.

Reads each level_kk/<mask>.pkl, converts the indices field from a list of
(upper, eligible) tuples into two separate arrays, and writes everything to
the new location as compressed npz.

The original data/values/ files are left in place. Once you've verified the
new shards work (e.g. by re-running value_iteration or opening one in the
state_explorer notebook), you can delete data/values/ manually.

Run from project root:
    python migrate_values.py
"""
import os
import pickle

import numpy as np
from tqdm import tqdm

from state_properties import save_shard


OLD_VALUES_DIR = "data/values"


def migrate_one(old_path: str, level: int, mask: int) -> None:
    with open(old_path, "rb") as f:
        payload = pickle.load(f)

    indices = payload["indices"]
    upper_total = np.array([u for u, _ in indices], dtype=np.uint8)
    yahtzee_eligible = np.array([e for _, e in indices], dtype=bool)

    save_shard(
        level, mask,
        merge=False,
        upper_total=upper_total,
        yahtzee_eligible=yahtzee_eligible,
        V=np.asarray(payload["V"]),
        decisions_A=np.asarray(payload["decisions_A"]),
        decisions_B=np.asarray(payload["decisions_B"]),
        decisions_C=np.asarray(payload["decisions_C"]),
        ev_A=np.asarray(payload["ev_A"]),
        ev_B=np.asarray(payload["ev_B"]),
        ev_C=np.asarray(payload["ev_C"]),
    )


def migrate_all() -> None:
    if not os.path.isdir(OLD_VALUES_DIR):
        print(f"{OLD_VALUES_DIR}/ not found; nothing to migrate.")
        return

    files = []
    for entry in sorted(os.listdir(OLD_VALUES_DIR)):
        level_dir = os.path.join(OLD_VALUES_DIR, entry)
        if not (entry.startswith("level_") and os.path.isdir(level_dir)):
            continue
        level = int(entry[len("level_"):])
        for fn in sorted(os.listdir(level_dir)):
            if not fn.endswith(".pkl"):
                continue
            mask = int(fn[:-4], 2)
            files.append((os.path.join(level_dir, fn), level, mask))

    print(f"Migrating {len(files)} shards from {OLD_VALUES_DIR}/ "
          "to data/state_properties/...")
    for path, level, mask in tqdm(files):
        migrate_one(path, level, mask)
    print("Done. Verify, then delete data/values/ when ready.")


if __name__ == "__main__":
    migrate_all()