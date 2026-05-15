import os
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from game_state import GameState

def _worker_enumerate_chunk(states_chunk):
    local = set()
    for state in tqdm(states_chunk, leave=False):
        for _, successor in state.get_all_successors():
            local.add(successor)
    return local

def enumerate_reachable_states(num_workers=None, batch_size=10000, start_level=0, save_pickles=False) -> list[set[GameState]]:
    if num_workers is None:
        num_workers = os.cpu_count()

    os.makedirs("data/state_levels/tmp", exist_ok=True)

    states_by_level = [set() for _ in range(14)]

    if start_level == 0:
        states_by_level[0].add(GameState(filled_mask=0, upper_total=0, lower_total=0, num_yahtzees=0))
        if save_pickles:
            with open("data/state_levels/level_0.pkl", "wb") as f:
                pickle.dump(states_by_level[0], f)
    else:
        with open(f"data/state_levels/level_{start_level}.pkl", "rb") as f:
            states_by_level[start_level] = pickle.load(f)

    for level in range(start_level, 13):
        current = list(states_by_level[level])
        batches = [current[i:i + batch_size] for i in range(0, len(current), batch_size)]

        print(f"level {level:2d} -> {level + 1:2d}: {len(current):>9,} states, {len(batches)} batches")

        # Free current level from memory before workers start
        states_by_level[level] = set()

        futures = {}
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(_worker_enumerate_chunk, batch): i
                       for i, batch in tqdm(enumerate(batches))}
            for future in tqdm(as_completed(futures), total=len(futures)):
                i = futures[future]
                chunk_result = future.result()
                path = f"data/state_levels/tmp/level_{level}_batch_{i}.pkl"
                with open(path, "wb") as f:
                    pickle.dump(chunk_result, f, protocol=pickle.HIGHEST_PROTOCOL)
                del chunk_result

        print("merging...")
        next_level = set()
        for i in tqdm(range(len(batches))):
            path = f"data/state_levels/tmp/level_{level}_batch_{i}.pkl"
            with open(path, "rb") as f:
                next_level |= pickle.load(f)
            os.remove(path)

        states_by_level[level + 1] = next_level

        if save_pickles:
            with open(f"data/state_levels/level_{level + 1}.pkl", "wb") as f:
                pickle.dump(next_level, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(13, len(states_by_level[-1]))

    return states_by_level

if __name__ == "__main__":
    levels = enumerate_reachable_states(save_pickles=True, start_level=5, num_workers=10)
    total = sum(len(s) for s in levels)
    print(f"\ntotal reachable states: {total:,}")