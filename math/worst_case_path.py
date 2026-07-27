"""Worst-case (minimum) final score under the POINT-MAXIMIZING policy — and the
turn-by-turn sequence that produces it.

PROTOTYPE. The EV-optimal policy is already solved (decisions_A/B/C in the
state_properties shards). Here the player NEVER deviates from it — every keep and
category is forced by that policy — but the DICE are adversarial: at each roll the
unluckiest outcome is chosen, so as to minimize the FINAL total. We want the
smallest total reachable that way, and the play-out that achieves it.

Why this is a shortest path (exact, not a heuristic):
  * The game is Markov in the ReducedGameState (mask, upper_total, yahtzee_eligible)
    — the policy depends only on it — so states, not histories, are the nodes.
  * Each turn is one edge S -> S': from S the adversary may see ANY initial roll,
    the policy forces a keep (decisions_A), then ANY reroll, forces a keep
    (decisions_B), then ANY final roll, forces a category (decisions_C). The edge
    cost is that turn's reward (box points + any +35 top / +100 joker bonus), which
    is >= 0. For a fixed successor S', only the CHEAPEST qualifying final roll
    matters (same S' => same future).
  * All rewards >= 0 and the graph is a DAG by level (one box filled per turn), so
    Dijkstra from the empty card, stopping at the first full-card state popped, is
    the exact minimum total. Parent pointers reconstruct the play-out.

Everything is SOURCED, no re-derived math: forced decisions come from the solved
shards (via state_explorer.get_state_row); reachability from precomputed
REROLL_OUTCOMES; each turn's reward + next state from
ReducedGameState.fill_by_idx (the house transition). No new scoring/EV is written.

Run from math/ with the ROOT venv (needs numpy):
    ../.venv/bin/python worst_case_path.py
"""
import argparse
import heapq
import itertools
import time

import numpy as np

from constants import CATEGORY_NAMES
from precomputed import REROLL_OUTCOMES, dice_idx_to_values, NUM_DICE_STATES
from reduced_game_state import ReducedGameState
from state_explorer import get_state_row, keep_to_values, load_payload_for_state

FULL_MASK = (1 << 13) - 1
START = ReducedGameState(filled_mask=0, upper_total=0, yahtzee_eligible=False)

# mask -> (decisions_A_all, decisions_B_all, decisions_C_all, {(upper, eligible): row})
_SHARD = {}


def _state_decisions(state):
    """Forced optimal keeps/category for `state`, read (and cached) from the shard
    holding its mask. Returns (dec_A, dec_B, dec_C), each a length-252 int array
    indexed by dice_idx."""
    m = state.filled_mask
    entry = _SHARD.get(m)
    if entry is None:
        p = load_payload_for_state(state)
        decA = np.asarray(p["decisions_A"], dtype=np.int32)
        decB = np.asarray(p["decisions_B"], dtype=np.int32)
        decC = np.asarray(p["decisions_C"], dtype=np.int32)
        ut = np.asarray(p["upper_total"], dtype=np.int32)
        ye = np.asarray(p["yahtzee_eligible"], dtype=bool)
        rowmap = {(int(ut[i]), bool(ye[i])): i for i in range(len(ut))}
        entry = (decA, decB, decC, rowmap)
        _SHARD[m] = entry
    decA, decB, decC, rowmap = entry
    r = rowmap[(int(state.upper_total), bool(state.yahtzee_eligible))]
    return decA[r], decB[r], decC[r]


def _transitions(state):
    """{next_state: (reward, (d0, d1, d2, category))} — one entry per successor
    reachable in a turn under the forced policy, keeping the CHEAPEST final roll
    that lands on each successor. d0/d1/d2 = initial/second/final roll (dice_idx)."""
    decA, decB, decC = _state_decisions(state)

    # Every initial roll d0 is possible; the policy forces keep decA[d0]. Collect
    # each reachable second-roll d1 with a witnessing d0.
    d1_from = {}
    for d0 in range(NUM_DICE_STATES):
        finals, _ = REROLL_OUTCOMES[(d0, int(decA[d0]))]
        for f in finals:
            d1_from.setdefault(int(f), d0)

    # From each reachable d1 (forced keep decB[d1]) collect each reachable final d2.
    d2_from = {}
    for d1 in d1_from:
        finals, _ = REROLL_OUTCOMES[(d1, int(decB[d1]))]
        for f in finals:
            d2_from.setdefault(int(f), d1)

    best = {}
    for d2, d1 in d2_from.items():
        c = int(decC[d2])
        is_joker, _ = state.legal_categories_by_idx(d2)
        reward, ns = state.fill_by_idx(c, d2, is_joker)
        cur = best.get(ns)
        if cur is None or reward < cur[0]:
            best[ns] = (reward, (d1_from[d1], d1, d2, c))
    return best


def worst_path(start=START, max_expanded=5_000_000, verbose=True):
    """Dijkstra to the cheapest full-card state. Returns (score, trajectory) where
    trajectory is a list of (state, reward, (d0, d1, d2, category)) per turn."""
    dist = {start: 0}
    parent = {start: None}
    pedge = {start: None}
    tie = itertools.count()
    heap = [(0, next(tie), start)]
    expanded = 0
    t0 = time.time()

    goal = None
    while heap:
        d, _, s = heapq.heappop(heap)
        if d > dist[s]:
            continue
        if s.filled_mask == FULL_MASK:
            goal = s
            break
        expanded += 1
        if expanded > max_expanded:
            raise RuntimeError(f"expanded > {max_expanded:,}; raise --max-expanded")
        if verbose and expanded % 20000 == 0:
            print(f"  expanded {expanded:,}  frontier {len(heap):,}  "
                  f"best-so-far dist {d}  ({time.time() - t0:.0f}s)")
        for ns, (r, wit) in _transitions(s).items():
            nd = d + r
            if nd < dist.get(ns, np.inf):
                dist[ns] = nd
                parent[ns] = s
                pedge[ns] = (r, wit)
                heapq.heappush(heap, (nd, next(tie), ns))

    if goal is None:
        raise RuntimeError("no full-card state reached")

    # Walk parents back to the start, then reverse into play order.
    traj = []
    node = goal
    while parent[node] is not None:
        r, wit = pedge[node]
        traj.append((parent[node], r, wit))
        node = parent[node]
    traj.reverse()
    if verbose:
        print(f"  done: expanded {expanded:,} states in {time.time() - t0:.0f}s\n")
    return dist[goal], traj


def _fmt_dice(idx):
    return "".join(str(v) for v in dice_idx_to_values(int(idx)))


def _fmt_keep(keep_idx):
    vals = keep_to_values(int(keep_idx))
    return "".join(str(v) for v in vals) if vals else "(reroll all)"


def print_trajectory(score, traj):
    print(f"Worst possible final score under the point-maximizing strategy: {score}\n")
    header = f"{'#':>2}  {'roll1':>5} {'keep1':>11}  {'roll2':>5} {'keep2':>11}  {'final':>5}  {'category':<14} {'pts':>3}  {'total':>5}"
    print(header)
    print("-" * len(header))
    running = 0
    for i, (state, reward, (d0, d1, d2, c)) in enumerate(traj, 1):
        decA, decB, decC = _state_decisions(state)
        running += reward
        print(f"{i:>2}  {_fmt_dice(d0):>5} {_fmt_keep(decA[d0]):>11}  "
              f"{_fmt_dice(d1):>5} {_fmt_keep(decB[d1]):>11}  {_fmt_dice(d2):>5}  "
              f"{CATEGORY_NAMES[c]:<14} {reward:>3}  {running:>5}")
    print(f"\n(pts = turn reward, i.e. box points plus any +35 top / +100 joker bonus)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-expanded", type=int, default=5_000_000,
                    help="safety cap on Dijkstra expansions (default 5,000,000)")
    args = ap.parse_args()
    score, traj = worst_path(max_expanded=args.max_expanded)
    print_trajectory(score, traj)


if __name__ == "__main__":
    main()
