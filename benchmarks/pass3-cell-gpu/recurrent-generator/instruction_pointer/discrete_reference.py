"""Cell Stream comparison using the historical prefix weights and only an explicit single source anchor."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import torch

from cell_stream import CellStream
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from train_reachability import Prefix
from transaction_native import execute


class AnchorStream(CellStream):
    def score_children(self, h, depth, paths, parents):
        scores, z = self.logits(h, depth, paths)
        if depth + 1 < len(self.roles):
            scores = torch.maximum(
                scores, self.prefix(self.prefix.evidence(self, depth, paths, z, look=False))
            )
        return scores, z


class Reference:
    def __init__(self, original_order=False, run_request_cap=None):
        self.run_request_cap = run_request_cap
        self.original_order = original_order
        self.prefix = Prefix().eval()
        self.prefix.load_state_dict(torch.load("run-recall/structural-reach/prefix.pt", weights_only=True))

    def make_stream(self, rd, model, rule, watermark, stats, order):
        return AnchorStream(rd, model, rule, watermark, stats, order=order)

    def scheduled_rules(self, frame, stats):
        return frame["rules"]

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        remaining = self.run_request_cap
        for r, wm in self.scheduled_rules(frame, stats):
            order = list(rd.order(r))
            semi = rd.iface.rules[r]["metadata"]["seminaive"]
            for anchor in order if semi and order else [None]:
                if perf_counter() >= deadline:
                    raise TimeoutError
                if anchor is not None:
                    t = rd.tabs[rd.iface.roles[r][anchor][0]]
                    # Single-source S1. All partners remain visible, including other new sources.
                    stats["source_version_reads"] += len(rd.live[t])
                    roots = [a for a in rd.live[t] if rd.store.visible[a]["version"] >= wm]
                    if not roots:
                        continue
                    seq = order if self.original_order else [anchor] + [v for v in order if v != anchor]
                else:
                    if not order and semi and wm:
                        continue
                    seq = order
                stream = self.make_stream(rd, model, r, wm, stats, tuple(seq))
                stream.prefix = self.prefix
                stream.semi = False
                if anchor is not None:
                    stream.roles[seq.index(anchor)] = roots
                for paths in stream.path_batches("stream", 0.0, deadline):
                    if remaining is None:
                        txn.proofs_from_paths(stream, paths)
                    else:
                        chunk = paths[:remaining]
                        txn.proofs_from_paths(stream, chunk)
                        remaining -= len(chunk)
                        if remaining == 0:
                            return


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ("root", "out"):
        p.add_argument(arg, type=Path)
    p.add_argument("case")
    p.add_argument("--block", type=int, default=0)
    p.add_argument("--seconds", type=int, default=180)
    p.add_argument("--original-order", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    d = folder(a.root, a.case)
    with TemporaryDirectory(dir=a.out) as tmp:
        path = Path(tmp) / "ref.json"
        target = Target(read(d / "program.json"), snapshot(a.root, d, "reference", "-", None, path)[0])
        initial = target.match(snapshot(a.root, d, "reference", "-", 0, path)[0])
        s = perf_counter()
        policy = Reference(a.original_order)
        setup = perf_counter() - s
        row = execute(a.root, a.case, study=policy, series=tmp, seconds=a.seconds)
        covered = target.match(read(Path(tmp) / (a.case + "-stream-multi") / "state.json")) - initial
        row.pop("trace", None)
        row.update(
            covered=len(covered),
            facts=sorted(covered),
            reference=len(target.gold) - len(initial),
            cold_wall=row["wall"] + row["runtime_setup_seconds"] + setup,
        )
        row["cold_eps"] = row["signed_ops"] / row["cold_wall"]
        (
            a.out / f"{a.case}__reference{'-source-order' if a.original_order else ''}_b{a.block}.json"
        ).write_text(json.dumps(row, indent=2))
        print(a.case, row["termination"], len(covered), row["paid"], row["cold_wall"], flush=True)
