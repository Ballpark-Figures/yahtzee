"""Reach probability + expected final points of every full GameState under optimal
play, and downstream analyses (coverage thresholds; per-level pairwise difference
distribution of rounded expected points).

The state is the FIRST reduction (== math/game_state.GameState):
    (filled_mask, upper_total, lower_total, num_yahtzees)      -- upper/lower UNCAPPED
i.e. bottom kept as a subtotal, not per-box. NOT ReducedGameState.

Forward pass over the full-state DAG under the already-computed optimal policy;
composes existing data, no new game math, no new state definition:
  * transition probs   : data/turn_kernels/level_kk/<mask>.npz  (grouped optimal
                         outcomes; prob = numerator / 7776**3)
  * reduced row + value: data/state_properties/level_kk/<mask>.npz
                         (upper_total capped 63, yahtzee_eligible, V)

Reachable full states are DISCOVERED as mass flows (no dependence on the heavy
data/state_levels/ enumeration). Each level's reach sums to 1 (checked).

    expected_final(state) = locked + V(reduced projection)
      locked = upper + (35 if upper>=63) + lower + 100*max(num_yahtzees-1, 0)
      V      = optimal rest-of-game EV of the reduced state (0 at the terminal level)

num_yahtzees per grouped outcome (kernel drops the dice roll -> reconstruct exactly):
    first Yahtzee : category == YAHTZEE and box_points == 50          -> num_y = 1
    extra Yahtzee : (reward - box_points) >= 100 (the +100 joker bonus, != 35 upper)
                                                                      -> num_y += 1

CLI (run from math/ with the ROOT venv):
    ../.venv/bin/python state_reach_coverage.py            # coverage + totals table
    ../.venv/bin/python state_reach_coverage.py --diffs    # + difference-distribution summary
Or import forward_reach()/coverage_table()/diff_distribution() (see notebooks/).
"""
from __future__ import annotations

import argparse

import numpy as np

from constants import (
    SIXES, YAHTZEE, YAHTZEE_POINTS, EXTRA_YAHTZEE_BONUS,
    UPPER_BONUS, UPPER_BONUS_THRESHOLD,
)
from turn_kernel import load_turn_kernel
from state_properties import load_shard

THRESHOLDS = (0.5, 0.9, 0.99, 0.999, 0.9999)
TERMINAL = 13

_LO_BITS, _NY_BITS = 9, 4  # pack upper<128, lower<512, num_y<16 into one int64


def _pack(up, lo, ny):
    return (up.astype(np.int64) << (_LO_BITS + _NY_BITS)) | (lo.astype(np.int64) << _NY_BITS) | ny.astype(np.int64)


def _unpack(key):
    ny = key & ((1 << _NY_BITS) - 1)
    lo = (key >> _NY_BITS) & ((1 << _LO_BITS) - 1)
    up = key >> (_LO_BITS + _NY_BITS)
    return up, lo, ny


def _row_lut(props):
    """Array indexed by (upper_cap*2 + eligible) -> row in this (level, mask) shard."""
    up = props["upper_total"].astype(np.int64)      # already capped at 63
    el = props["yahtzee_eligible"].astype(np.int64)
    lut = np.full(64 * 2, -1, dtype=np.int64)
    lut[up * 2 + el] = np.arange(len(up))
    return lut


def _rows_for(lut, up, ny):
    rows = lut[np.minimum(up, 63) * 2 + (ny >= 1).astype(np.int64)]
    if (rows < 0).any():
        raise AssertionError("a full state projects to a missing reduced row")
    return rows


def _locked(up, lo, ny):
    """Points already committed = GameState.total_score() of the partial card."""
    bonus = np.where(up >= UPPER_BONUS_THRESHOLD, UPPER_BONUS, 0)
    yz = EXTRA_YAHTZEE_BONUS * np.maximum(ny - 1, 0)
    return up + bonus + lo + yz


def _transition(mask, up, lo, ny, reach, lut, kernel):
    """Every one-turn contribution out of (mask, states): -> (next_mask, up',lo',ny',reach')."""
    offs = kernel["offsets"].astype(np.int64)
    cat = kernel["category"].astype(np.int64)
    bp = kernel["box_points"].astype(np.int64)
    rw = kernel["reward"].astype(np.int64)
    p_out = kernel["numerator"].astype(np.float64) / float(kernel["denom"])

    rows = _rows_for(lut, up, ny)
    n_out = offs[rows + 1] - offs[rows]
    total = int(n_out.sum())
    state_idx = np.repeat(np.arange(len(up)), n_out)
    prefix = np.zeros(len(up), np.int64)
    np.cumsum(n_out[:-1], out=prefix[1:])
    o_idx = offs[rows][state_idx] + (np.arange(total) - prefix[state_idx])

    c, b, r, p = cat[o_idx], bp[o_idx], rw[o_idx], p_out[o_idx]
    su, sl, sy, sr = up[state_idx], lo[state_idx], ny[state_idx], reach[state_idx]

    is_upper = c <= SIXES
    n_up = su + np.where(is_upper, b, 0)
    n_lo = sl + np.where(is_upper, 0, b)
    first_yz = (c == YAHTZEE) & (b == YAHTZEE_POINTS)
    extra_yz = (r - b) >= EXTRA_YAHTZEE_BONUS
    n_ny = np.where(first_yz, 1, np.where(extra_yz, sy + 1, sy)).astype(np.int64)

    return mask | (1 << c), n_up, n_lo, n_ny, sr * p


def forward_reach(max_level: int = TERMINAL, verbose: bool = False) -> list[dict]:
    """Forward pass. Returns per_level[k] = dict of aligned numpy arrays:
        mask, upper, lower, num_yahtzees, reach, expected_final
    for every optimal-play-reachable full GameState at level k (reach sums to 1)."""
    cur = {0: (np.zeros(1, np.int64),) * 3 + (np.ones(1),)}
    per_level: list[dict] = []

    for level in range(min(max_level, TERMINAL) + 1):
        cols = {k: [] for k in ("mask", "upper", "lower", "num_yahtzees", "reach", "expected_final")}
        buckets: dict[int, list] = {}

        for mask, (up, lo, ny, reach) in cur.items():
            if level < TERMINAL:
                props = load_shard(level, mask)
                lut = _row_lut(props)
                V = props["V"][_rows_for(lut, up, ny)].astype(np.float64)
            else:
                V = 0.0                                   # terminal: no future
            ef = _locked(up, lo, ny) + V

            cols["mask"].append(np.full(len(up), mask, np.int64))
            cols["upper"].append(up); cols["lower"].append(lo)
            cols["num_yahtzees"].append(ny); cols["reach"].append(reach)
            cols["expected_final"].append(ef)

            if level < TERMINAL and level < max_level:
                nmask, n_up, n_lo, n_ny, n_reach = _transition(
                    mask, up, lo, ny, reach, lut, load_turn_kernel(level, mask))
                order = np.argsort(nmask, kind="stable")
                nmask_s = nmask[order]
                uniq, starts = np.unique(nmask_s, return_index=True)
                bnds = np.append(starts, len(nmask_s))
                for i, m in enumerate(uniq):
                    sl = order[bnds[i]:bnds[i + 1]]
                    buckets.setdefault(int(m), [[], [], [], []])
                    b = buckets[int(m)]
                    b[0].append(n_up[sl]); b[1].append(n_lo[sl]); b[2].append(n_ny[sl]); b[3].append(n_reach[sl])

        per_level.append({k: np.concatenate(v) for k, v in cols.items()})
        if verbose:
            r = per_level[-1]["reach"]
            print(f"  level {level:2d}: {len(r):>11,} states, reach_sum={r.sum():.9f}")

        if level == TERMINAL or level == max_level:
            break
        nxt = {}
        for m, lists in buckets.items():
            up = np.concatenate(lists[0]); lo = np.concatenate(lists[1])
            ny = np.concatenate(lists[2]); rc = np.concatenate(lists[3])
            uk, inv = np.unique(_pack(up, lo, ny), return_inverse=True)
            agg = np.zeros(len(uk)); np.add.at(agg, inv, rc)
            u2, l2, y2 = _unpack(uk)
            nxt[m] = (u2, l2, y2, agg)
        cur = nxt

    return per_level


def _coverage(reach, thresholds=THRESHOLDS):
    total = reach.sum()
    csum = np.cumsum(np.sort(reach)[::-1])
    return {t: min(int(np.searchsorted(csum, t * total, side="left")) + 1, len(reach)) for t in thresholds}


def coverage_table(per_level, thresholds=THRESHOLDS) -> dict:
    """Per level: {'n_states', threshold: count}; plus 'total' row (sums over levels)."""
    out, totals, n_all = {}, {t: 0 for t in thresholds}, 0
    for lvl, d in enumerate(per_level):
        cov = _coverage(d["reach"], thresholds)
        out[lvl] = {"n_states": len(d["reach"]), **cov}
        n_all += len(d["reach"])
        for t in thresholds:
            totals[t] += cov[t]
    out["total"] = {"n_states": n_all, **totals}
    return out


def diff_distribution(per_level) -> dict:
    """Per level: np.array `d` where d[n] = number of UNORDERED pairs of states whose
    rounded expected finals differ by exactly n (n=0 -> distinct states, same value)."""
    out = {}
    for lvl, d in enumerate(per_level):
        v = np.rint(d["expected_final"]).astype(np.int64)
        h = np.bincount(v).astype(np.int64)              # histogram over rounded EV
        ac = np.correlate(h, h, mode="full")[len(h) - 1:]  # ac[n] = sum_v h[v]*h[v+n]
        n_states = int(h.sum())
        pairs = ac.copy()
        pairs[0] = (ac[0] - n_states) // 2               # unordered distinct same-value pairs
        out[lvl] = pairs
    return out


def _print_coverage(tbl):
    ts = [k for k in tbl[0] if k != "n_states"]
    hdr = "  ".join(f"{t*100:>7g}%" for t in ts)
    print(f"{'level':>5}  {'#states':>11}  {hdr}")
    for lvl in range(TERMINAL + 1):
        if lvl not in tbl:
            continue
        row = tbl[lvl]
        print(f"{lvl:>5}  {row['n_states']:>11,}  " + "  ".join(f"{row[t]:>8,}" for t in ts))
    tot = tbl["total"]
    print(f"{'TOT':>5}  {tot['n_states']:>11,}  " + "  ".join(f"{tot[t]:>8,}" for t in ts)
          + "   <- #states = total optimal play reaches")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-level", type=int, default=TERMINAL)
    ap.add_argument("--diffs", action="store_true", help="also print a diff-distribution summary")
    args = ap.parse_args()

    print("Forward pass over the full-state DAG…")
    pl = forward_reach(args.max_level, verbose=True)
    print()
    _print_coverage(coverage_table(pl))

    if args.diffs:
        print("\nPairwise difference distribution (rounded expected finals):")
        dd = diff_distribution(pl)
        for lvl in sorted(dd):
            d = dd[lvl]
            nz = np.nonzero(d)[0]
            span = nz[-1] if len(nz) else 0
            print(f"  level {lvl:2d}: max diff {span:4d}, "
                  f"pairs(0)={d[0]:,}, total pairs={int(d.sum()):,}")
