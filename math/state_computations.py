import os
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from game_state import GameState


def mask_to_filename(filled_mask: int) -> str:
    return format(filled_mask, '013b') + '.pkl'


def filename_to_mask(filename: str) -> int:
    return int(os.path.splitext(filename)[0], 2)


def get_level_dir(level: int) -> str:
    return f"data/state_levels/level_{level:02d}"


def _worker_expand_mask(level: int, filled_mask: int) -> dict[int, set[GameState]]:
    path = os.path.join(get_level_dir(level), mask_to_filename(filled_mask))
    with open(path, 'rb') as f:
        states = pickle.load(f)

    results = {}
    for state in tqdm(states, leave=False):
        for _, successor in state.get_all_successors():
            mask = successor.filled_mask
            if mask not in results:
                results[mask] = set()
            results[mask].add(successor)

    return results


def enumerate_reachable_states(num_workers: int = None, start_level: int = 0) -> None:
    if num_workers is None:
        num_workers = os.cpu_count()

    if start_level == 0:
        level_dir = get_level_dir(0)
        os.makedirs(level_dir, exist_ok=True)
        initial = GameState(filled_mask=0, upper_total=0, lower_total=0, num_yahtzees=0)
        with open(os.path.join(level_dir, mask_to_filename(0)), 'wb') as f:
            pickle.dump({initial}, f, protocol=pickle.HIGHEST_PROTOCOL)

    for level in range(start_level, 13):
        level_dir = get_level_dir(level)
        next_level_dir = get_level_dir(level + 1)
        os.makedirs(next_level_dir, exist_ok=True)

        masks = [
            filename_to_mask(f)
            for f in os.listdir(level_dir)
            if f.endswith('.pkl')
        ]

        print(f"level {level:2d} -> {level + 1:2d}: {len(masks)} masks")

        next_level_counts = {}
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(_worker_expand_mask, level, mask): mask
                for mask in tqdm(masks)
            }
            for future in tqdm(as_completed(futures), total=len(futures)):
                for successor_mask, successor_states in future.result().items():
                    path = os.path.join(next_level_dir, mask_to_filename(successor_mask))
                    if os.path.exists(path):
                        with open(path, 'rb') as f:
                            existing = pickle.load(f)
                        existing |= successor_states
                        with open(path, 'wb') as f:
                            pickle.dump(existing, f, protocol=pickle.HIGHEST_PROTOCOL)
                        next_level_counts[successor_mask] = len(existing)
                    else:
                        with open(path, 'wb') as f:
                            pickle.dump(successor_states, f, protocol=pickle.HIGHEST_PROTOCOL)
                        next_level_counts[successor_mask] = len(successor_states)

        total = sum(next_level_counts.values())
        print(f"level {level + 1:2d}: {len(next_level_counts)} masks, {total:,} states")


if __name__ == "__main__":
    enumerate_reachable_states(start_level=0, num_workers=8)