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

def enumerate_reachable_states(num_workers=None, save_pickles: bool=False) -> list[set[GameState]]:
    if num_workers is None:
        num_workers = os.cpu_count()
    print("hello", num_workers)
    
    initial = GameState(filled_mask=0, upper_total=0, lower_total=0, num_yahtzees=0)
    states_by_level = [set() for _ in range(14)]
    states_by_level[0].add(initial)

    if save_pickles:
        with open(f"data/state_levels/level_0.pkl", "wb") as f:
            pickle.dump(states_by_level[0], f)

    for level in range(13):
        current = list(states_by_level[level])
        chunks = [current[i::num_workers] for i in range(num_workers)]

        next_level = states_by_level[level + 1]

        print(level, len(current))

        next_level = set()
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(_worker_enumerate_chunk, chunk) for chunk in tqdm(chunks, leave=False)]
            for future in tqdm(as_completed(futures), total=len(futures)):
                next_level |= future.result()

        states_by_level[level + 1] = next_level

        if save_pickles:
            with open(f"data/state_levels/level_{level + 1}.pkl", "wb") as f:
                pickle.dump(next_level, f, protocol=pickle.HIGHEST_PROTOCOL)
        
    print(13, len(states_by_level[-1]))
    
    return states_by_level

if __name__ == "__main__":
    levels = enumerate_reachable_states(save_pickles=True)
    total = sum(len(s) for s in levels)
    print(f"\ntotal reachable states: {total:,}")