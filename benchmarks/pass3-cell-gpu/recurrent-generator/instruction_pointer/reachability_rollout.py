"""Ablate routing and admission on live independent CCP executions."""

import argparse
from pathlib import Path
import torch
from cell_stream import CellStream
from generation_frontier import Generator
from protocol_experiment import dump
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from transaction_native import execute
from txn_policy import ResponseStream


class ReachStream(ResponseStream):
    def children(self, paths, depth, block):
        if self.study.dense:
            yield from CellStream.children(self, paths, depth, block)
        else:
            yield from super().children(paths, depth, block)

    def score_children(self, h, depth, paths, parents):
        score, z = super().score_children(h, depth, paths, parents)
        last = depth + 1 == len(self.roles)
        if (last and self.study.terminal_open) or (not last and self.study.prefix_open):
            self.stats["rescued_final" if last else "rescued_prefix"] += int(
                (score < 0).sum()
            )
            score = torch.zeros_like(score)
        elif not last and self.study.relaxed:
            score = score + 1
        elif not last and self.study.adapter is not None:
            before = score
            features = self.study.adapter.evidence(
                self, depth, paths, z, look=not self.study.no_look
            )
            score = torch.maximum(score, self.study.adapter(features))
            self.stats["learned_prefix_additions"] += int(
                ((before < 0) & (score >= 0)).sum()
            )
        return score, z


def run(root, out, case, arm, seconds, repeat=0):
    policy = Generator(root, "A", 0, case)
    policy.stream_type = ReachStream
    policy.terminal_open = arm in (
        "terminal",
        "terminal-prefix",
        "terminal-dense",
        "open",
    )
    policy.prefix_open = arm in ("prefix", "terminal-prefix", "open")
    policy.dense = arm in ("dense", "terminal-dense", "open")
    policy.relaxed = arm == "relaxed"
    policy.no_look = arm == "learned-nolook"
    policy.adapter = None
    if arm in ("learned", "learned-nolook"):
        from train_reachability import Prefix

        policy.adapter = Prefix().eval()
        policy.adapter.load_state_dict(torch.load(out / "prefix.pt", weights_only=True))
    series = f"structural-reach/{arm}"
    m = execute(root, case, study=policy, series=series, seconds=seconds)
    work = root / series / (case + "-stream-multi")
    d = folder(root, case)
    path = work / "align.json"
    target = Target(
        read(d / "program.json"), snapshot(root, d, "reference", "-", None, path)[0]
    )
    seed = target.match(snapshot(root, d, "reference", "-", 0, path)[0])
    derived = target.match(read(work / "state.json")) - seed
    old = set()
    thresholds_found = 0
    for cut in (-6, -3, -1, 0, 1, 3):
        prev = (
            root
            / "generation-frontier"
            / f"A-{cut:g}"
            / (case + "-stream-multi")
            / "state.json"
        )
        if prev.exists():
            thresholds_found += 1
            old |= target.match(read(prev)) - seed
    m.pop("trace")
    m.pop("guard_failures")
    m.update(
        arm=arm,
        repeat=repeat,
        reference=len(target.gold) - len(seed),
        derived=len(derived),
        threshold_states_found=thresholds_found,
        union_A=len(old),
        extra=len(derived - old),
        missing=len(old - derived),
        seconds_budget=seconds,
    )
    dump(out / f"reach-{case}-{arm}-{repeat}.json", m)
    print(
        case,
        arm,
        m["termination"],
        m["runs"],
        len(derived),
        m["extra"],
        m["paid"],
        round(m["wall"], 2),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cases", nargs="+", required=True)
    p.add_argument("--arms", nargs="+", required=True)
    p.add_argument("--seconds", type=float, default=75)
    p.add_argument("--repeat", type=int, default=0)
    a = p.parse_args()
    torch.set_num_threads(1)
    a.out.mkdir(exist_ok=True, parents=True)
    for arm in a.arms:
        for c in a.cases:
            run(a.root, a.out, c, arm, a.seconds, a.repeat)
