"""Isolate the frozen Run 541 host proof under controlled memory growth."""

import argparse
import json
from collections import Counter
from pathlib import Path
from time import perf_counter_ns
from types import SimpleNamespace

import numpy as np
import torch

from cell_transaction import update_memory
from composition_relation import bits
from cost_bake import LearnedCostEntries
from entry_model import Family
from entry_wiring import use_wiring
from event_addresses import Directory
from recursive_ripsat_study import setup_policy
from recursive_rollout import get_policy

RULE, ROLE, WATERMARK = 498, 4, 489
SOURCE = (883892, 2)


def restore(reader, tape):
    with tape.open() as src:
        for line in src:
            frame = json.loads(line)
            reader.advance(frame)
            if frame["run"] == 541:
                if dict(frame["rules"])[RULE] != WATERMARK:
                    raise ValueError("unexpected rule watermark")
                return
    raise ValueError("missing native publication")


def measure(mem, bake, ix, paths):
    begin = perf_counter_ns()
    bake.choose(mem, RULE, ROLE, ix, True, WATERMARK)
    roots = bake.roots(ix)
    if not bake.active or not bake.selected[ix].all():
        raise ValueError("fixture changed frozen model action")
    width = 0
    if len(roots):
        order = mem.order(RULE, ROLE)
        d = bake.cut
        window = mem.window(RULE, order[:d], order[d], paths[:, :d])
        _, _, n = bake.window(mem, RULE, order, d, paths[:, :d], window, WATERMARK)
        width = int(n[0])
    return perf_counter_ns() - begin, len(roots), width


@torch.no_grad()
def run(data, store, case):
    state = torch.load(store / "structure-rl.pt", weights_only=True)
    directory, _, _, owner = setup_policy(
        data, store, "sum-divisors", state, True, policy_cls=LearnedCostEntries
    )
    reader = get_policy(data, directory, "free", "multi").reader
    restore(reader, store / "sum-divisors-native-memory.jsonl")
    stats = Counter()
    mem = Directory(reader, stats)
    order = mem.order(RULE, ROLE)
    source = mem.bank(mem.roles[RULE][ROLE])
    ix = np.array([source.positions[SOURCE]])
    if tuple(source.rows[ix[0]]) != (*SOURCE, 303):
        raise ValueError("wrong source")
    # A fixed all-old diagnostic prefix; remaining slot positions select visible named rows.
    paths = np.zeros((1, len(order)), dtype=np.int64)
    paths[0, 0] = ix[0]
    owner.family = Family(reader, owner.program, owner.manifest)
    use_wiring(owner.family, owner.graph)
    owner.count = Counter()
    owner.txn = SimpleNamespace(run=541)
    bake = owner.cost_bake
    dst = mem.roles[RULE][order[-1]]
    left, col, _, right = reader.iface.links(RULE, order[:-1], (order[-1],))[0]
    srcbank = mem.bank(mem.roles[RULE][left])
    bucket = srcbank.codes[paths[0, order.index(left)], col]
    other = next(
        t
        for t in sorted(reader.live)
        if t not in mem.roles[RULE]
        and reader.live[t]
        and len(reader.store.visible[next(iter(reader.live[t]))]["hashes"]) == 3
    )
    table = other if case == "other_table" else dst
    width = len(reader.store.visible[next(iter(reader.live[table]))]["hashes"])
    choices = torch.from_numpy(np.stack([bits(i) for i in range(512)]))
    wrong_hash = int(np.flatnonzero(reader.index.code(reader.index.encoder(choices)).numpy() != bucket)[0])
    baseline = measure(mem, bake, ix, paths)
    if baseline[1] != 0:
        raise ValueError("reference old root did not close")
    rows = []
    for n in (0, 256, 1024, 4096, 16384):
        # Independent publications grow one table; no added port is an input to the proof.
        previous = rows[-1]["extra_rows"] if rows else 0
        count = n - previous
        ids = np.arange(previous, n, dtype=np.int64)
        meta = np.zeros((count, 6), dtype=np.int64)
        meta[:, 0] = -(2 * ids + 900000001)
        meta[:, 2] = table
        meta[:, 3] = 500 if case != "role_old" else 400
        meta[:, 5] = np.arange(1, count + 1) * width
        hashes = np.full((count, width), wrong_hash, dtype=np.uint64)
        hashes[:, (right + 1) % width] = ids + 1000000
        if count and (int(meta[0, 0]), 0) in reader.store.visible:
            raise ValueError("address collision")
        old_writes = reader.index.writes
        start = perf_counter_ns()
        if count:
            update_memory(reader, {}, (meta, hashes.ravel(), (), ()), repair_types=())
        publication_ns = perf_counter_ns() - start
        before = stats.copy()
        old_positions = owner.count["cost_index_positions"]
        cold, kept, width_after = measure(mem, bake, ix, paths)
        warm = [measure(mem, bake, ix, paths)[0] for _ in range(9)]
        if width_after or kept != int(bool(n and case == "role_fresh_other_bucket")):
            raise ValueError((case, n, kept, width_after))
        rows.append(
            dict(
                case=case,
                extra_rows=n,
                published=count,
                table=table,
                input_refs=1,
                field_index_writes=reader.index.writes - old_writes,
                bank_rows=stats["index_port_reads"] - before["index_port_reads"],
                posting_rows=stats["posting_index_reads"] - before["posting_index_reads"],
                fresh_rank_rows=owner.count["cost_index_positions"] - old_positions,
                retained_roots=kept,
                returned_positions=width_after,
                publication_ns=publication_ns,
                first_proof_ns=cold,
                warm_proof_ns=warm,
            )
        )
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    args = p.parse_args()
    torch.set_num_threads(1)
    rows = [
        run(args.data, args.store, case)
        for _ in range(3)
        for case in ("other_table", "role_old", "role_fresh_other_bucket")
    ]
    (args.store / "boundary/growth.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
