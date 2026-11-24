"""Service all reachable prefixes, selecting a coarse or finer neural address at expansion."""

import argparse
from pathlib import Path
from time import perf_counter
import torch
from completion_training import Completion
from generation_frontier import Generator
from protocol_experiment import dump
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from transaction_native import execute
from txn_policy import ResponseStream
from reachability_rollout import ReachStream
from train_reachability import Prefix


class ServiceStream(ResponseStream):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.urgency = {}
        self.fine = {}

    def score_children(self, h, depth, paths, parents):
        score, z = super().score_children(h, depth, paths, parents)
        if depth + 1 < len(self.roles):
            if self.study.service in ("all-fine", "fresh-fine"):
                cold = torch.ones(len(paths), dtype=torch.bool)
            else:
                pred = self.study.completion(Completion.features(self, depth, paths, z))
                # Expected log completions per unit of expansion and the
                # probability that any continuation exists. Used for routing only.
                utility = pred[:, 0].sigmoid() * torch.exp(
                    (pred[:, 1] - pred[:, 2]).clamp(-12, 12)
                )
                cold = utility < 0.5
                self.stats["prefix_predictions"] += len(cold)
            self.urgency[depth + 1] = cold
            self.stats["deferred_prefixes"] += int(cold.sum())
            score = torch.zeros_like(score)
        return score, z

    def prepare_fine(self, depth):
        if depth in self.fine:
            return self.fine[depth]
        start = perf_counter()
        role, col, right = self.links[depth][0]
        src = torch.tensor([self.rd.index.rows[a][2][col] for a in self.roles[role]])
        dst = torch.tensor([self.rd.index.rows[a][2][right] for a in self.roles[depth]])
        if len(self.links[depth]) > 1:
            role2, c2, r2 = self.links[depth][1]
            extra_src = torch.tensor(
                [self.rd.index.rows[a][2][c2] for a in self.roles[role2]]
            )
            extra_dst = torch.tensor(
                [self.rd.index.rows[a][2][r2] for a in self.roles[depth]]
            )
        else:
            role2 = role
            # Both sides use the same cached neural field encoder and planes.
            planes = self.study.planes

            def finer(keys):
                return ((keys @ planes >= 0).long() * self.study.bits_weight).sum(1)

            extra_src = finer(self.tables[role][3][:, col])
            extra_dst = finer(self.tables[depth][3][:, right])
        ids = dst * 256 + extra_dst
        positions = torch.arange(len(ids))
        if (
            self.study.service in ("cached", "fresh-fine")
            and self.semi
            and depth + 1 == len(self.roles)
        ):
            young = self.tables[depth][0]
            ids = torch.cat((ids, ids[young] + 65536))
            positions = torch.cat((positions, positions[young]))
        order = ids.argsort(stable=True)
        self.fine[depth] = role, src, role2, extra_src, ids[order], positions[order]
        self.stats["fine_index_reads"] += (
            len(src) + len(dst) + len(extra_src) + len(extra_dst)
        )
        self.stats["fine_index_seconds"] += perf_counter() - start
        return self.fine[depth]

    def children(self, paths, depth, block):
        if not depth:
            yield from super().children(paths, depth, block)
            return
        cold = self.urgency[depth]
        if len(cold) != len(paths):
            raise AssertionError("lost pending prefix alignment")
        # Keep existing Response-derived queries, including chargeable computations.
        eligible = bool(self.links[depth]) and not self.programs(depth)
        if not eligible:
            self.stats["serviced_deferred"] += int(cold.sum())
            yield from super().children(paths, depth, block)
            return
        deferred = int(cold.sum())
        if self.study.service == "cached" and (depth in self.fine or deferred):
            cold = torch.ones_like(cold)
        hot = torch.where(~cold)[0]
        pending = torch.where(cold)[0]
        if len(hot):
            for parent, col in super().children(paths[hot], depth, block):
                yield hot[parent], col
        if not len(pending):
            return
        self.stats["serviced_deferred"] += deferred
        a, lo, b, hi, bank, order = self.prepare_fine(depth)
        q = lo[paths[pending, a]] * 256 + hi[paths[pending, b]]
        if (
            self.study.service in ("cached", "fresh-fine")
            and self.semi
            and depth + 1 == len(self.roles)
        ):
            fresh = torch.stack(
                [self.tables[j][0][paths[pending, j]] for j in range(depth)]
            ).any(0)
            q = q + 65536 * (~fresh).long()
        starts = torch.searchsorted(bank, q)
        lengths = torch.searchsorted(bank, q, right=True) - starts
        ends = lengths.cumsum(0)
        offset = ends - lengths
        self.stats["fine_lookups"] += len(q)
        self.stats["fine_postings"] += int(ends[-1])
        for n in range(0, int(ends[-1]), block):
            ix = torch.arange(n, min(n + block, int(ends[-1])))
            parent = torch.searchsorted(ends, ix, right=True)
            yield pending[parent], order[starts[parent] + ix - offset[parent]]


def run(root, out, case, arm, rep):
    g = Generator(root, "A", 0, case)
    if arm in ("local", "open"):
        g.stream_type = ReachStream
        g.dense = g.terminal_open = g.relaxed = False
        g.prefix_open = arm == "open"
        g.no_look = True
        g.adapter = None
        if arm == "local":
            g.adapter = Prefix().eval()
            g.adapter.load_state_dict(
                torch.load(
                    Path("run-recall/structural-reach/prefix.pt"), weights_only=True
                )
            )
    else:
        g.stream_type = ServiceStream
        g.service = arm
        g.completion = Completion().eval()
        g.completion.load_state_dict(
            torch.load(out / "continuation.pt", weights_only=True)
        )
        g.planes = torch.randn(24, 8, generator=torch.Generator().manual_seed(10219))
        g.bits_weight = 2 ** torch.arange(8)
    series = f"completion-service/{arm}/repeat-{rep}"
    m = execute(root, case, study=g, series=series, seconds=240)
    work = root / series / (case + "-stream-multi")
    d = folder(root, case)
    p = work / "compare.json"
    target = Target(
        read(d / "program.json"), snapshot(root, d, "reference", "-", None, p)[0]
    )
    seed = target.match(snapshot(root, d, "reference", "-", 0, p)[0])
    hits = target.match(read(work / "state.json")) - seed
    base = (
        target.match(
            read(
                root
                / "structural-reach/learned-nolook"
                / (case + "-stream-multi")
                / "state.json"
            )
        )
        - seed
    )
    assert m["termination"] == "schedule_end"
    w = m["work"]
    assert w.get("deferred_prefixes", 0) == w.get("serviced_deferred", 0)
    m.pop("trace")
    m.pop("guard_failures")
    m.update(
        arm=arm,
        rep=rep,
        coverage=len(hits),
        den=len(target.gold) - len(seed),
        extra=len(hits - base),
        lost=len(base - hits),
    )
    dump(out / f"service-{case}-{arm}-{rep}.json", m)
    print(case, arm, len(hits), m["paid"], m["wall"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cases", nargs="+", required=True)
    p.add_argument(
        "--arms", nargs="+", default=["local", "open", "learned", "all-fine"]
    )
    p.add_argument("--reps", type=int, default=4)
    p.add_argument("--offset", type=int, default=0)
    a = p.parse_args()
    torch.set_num_threads(1)
    for c in a.cases:
        for i in range(a.offset, a.offset + a.reps):
            for arm in a.arms if i % 2 == 0 else a.arms[::-1]:
                run(a.root, a.out, c, arm, i)
