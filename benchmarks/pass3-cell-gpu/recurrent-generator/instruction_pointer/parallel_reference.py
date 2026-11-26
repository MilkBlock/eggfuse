"""Score the historical Stream on precisely the joint models' frozen Runs."""

import json
from collections import Counter, defaultdict
from time import perf_counter

import torch

from discrete_cells import from_q
from discrete_draft import Cell
from discrete_reference import Reference
from metal_scaling import CASES
from parallel_budget import args
from recursive_rollout import get_policy
from recursive_train import folder, read


class WitnessScore:
    def __init__(self, known):
        self.known = known
        self.hits = set()
        self.total = 0

    def proofs_from_paths(self, stream, paths):
        self.total += len(paths)
        if stream.rule not in self.known:
            return
        refs = [None] * len(stream.order)
        for j, role in enumerate(stream.order):
            refs[role] = stream.port_refs(j)[paths[:, j]].tolist()
        for ix in range(len(paths)):
            c = Cell(stream.rule, tuple(tuple(values[ix]) for values in refs))
            if c in self.known[stream.rule]:
                self.hits.add(c)


@torch.no_grad()
def run(a):
    rows = []
    for case in CASES:
        selected = {x["run"] for x in read(a.out / f"frozen-{case}.json")}
        d = folder(a.data, case)
        witness = defaultdict(lambda: defaultdict(set))
        for q in read(d / "tape.json")["requests"]:
            witness[q["run"]][q["rule"]].add(from_q(q))
        pol = get_policy(a.data, d, "free", "multi")
        ref = Reference(original_order=True)
        with (d / "memory.jsonl").open() as f:
            for line in f:
                frame = json.loads(line)
                if frame["run"] > max(selected):
                    break
                pol.reader.advance(frame)
                r = frame["run"]
                if r not in selected:
                    continue
                score = WitnessScore(witness[r])
                stats = Counter()
                start = perf_counter()
                complete = True
                try:
                    ref.run_snapshot(
                        frame,
                        None,
                        pol.reader,
                        pol.model,
                        score,
                        stats,
                        start + a.seconds,
                    )
                except TimeoutError:
                    complete = False
                rows.append(
                    {
                        "case": case,
                        "run": r,
                        "known": sum(map(len, witness[r].values())),
                        "hits": len(score.hits),
                        "output": score.total,
                        "scored": stats["visits"],
                        "elapsed": perf_counter() - start,
                        "complete": complete,
                    }
                )
                print(case, r, rows[-1], flush=True)
    (a.out / "reference-frozen.json").write_text(json.dumps(rows) + "\n")


if __name__ == "__main__":
    p = args()
    p.add_argument("--seconds", type=float, default=120)
    torch.set_num_threads(1)
    run(p.parse_args())
