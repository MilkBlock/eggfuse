"""Same-state supervision for the frozen architecture. Native tapes supply positives only."""

import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from torch.nn.functional import binary_cross_entropy_with_logits

from continuation_audit import arguments
from discrete_cells import from_q
from metal_scaling import CASES, models
from recursive_train import binary, folder, read
from response_study import memory


def snapshots(a, case, source, make_memory=memory):
    d = folder(a.data, case)
    tape = (
        d / "tape.json"
        if source == "teacher"
        else a.corpus / "reference-stream" / (case + "-stream-multi") / "issued.json"
    )
    frames = (
        d / "memory.jsonl"
        if source == "teacher"
        else a.corpus / f"full-{case}-stream.jsonl"
    )
    audit = json.loads(
        subprocess.check_output(
            [
                binary(a.data),
                "replay",
                d / "program.json",
                tape,
                "audit",
                "--recall",
                tape,
                "--ept-origins",
            ]
        )
    )
    group = defaultdict(dict)
    requests = read(tape)["requests"]
    assert audit["counts"]["accepted"] == len(requests)
    verified = {
        (run, token)
        for run, token, owner, reason in audit["recall_verdicts"]
        if owner is not None and reason == "match"
    }
    if audit["unused_recall"] or verified != {(q["run"], q["token"]) for q in requests}:
        raise ValueError(f"snapshot verification failed for {case}/{source}")
    gains = dict(audit["ept"]["origins"])
    for q in requests:
        c = from_q(q)
        group[q["run"]][c] = group[q["run"]].get(c, 0) + gains.get(q["token"], 0)
    # Sample states by arity of the target set before looking at any predictions.
    bins = defaultdict(list)
    for r, g in group.items():
        bins[min(4, (len(g).bit_length() - 1) // 2)].append(r)
    rng = np.random.default_rng(219)
    selected = {
        int(r)
        for runs in bins.values()
        for r in rng.choice(runs, min(len(runs), 8), replace=False)
    }
    m = make_memory(a, d)
    with frames.open() as f:
        for line in f:
            frame = json.loads(line)
            m.update(frame)
            if frame["run"] in selected:
                yield m, frame["run"], group[frame["run"]]


@torch.no_grad()
def data(a, marks):
    rows = {"single": [], "multi": []}
    counts = Counter()
    for case, src in [
        ("sum", "teacher"),
        ("dot", "teacher"),
        ("grammar-benefit-fork-17118", "teacher"),
        ("sum", "stream"),
        ("grammar-benefit-fork-17118", "stream"),
    ]:
        for m, r, g in snapshots(a, case, src):
            one = []
            many = []
            counts["states"] += 1
            for c in g:
                records = []
                got = marks.draw(m, None, Counter(), target=c, records=records)
                counts["verified_bindings"] += 1
                if got != c:
                    counts["unrepresentable"] += 1
                    continue
                if not records:
                    counts["unambiguous"] += 1
                    continue
                seq = [(x, y, 1 / len(records)) for x, y, _ in records]
                if not one:
                    one = seq
                many.extend(seq)
            for arm, seq in [("single", one), ("multi", many)]:
                if seq:
                    x, y, w = zip(*seq)
                    rows[arm].append(
                        (torch.stack(x), torch.tensor(y).float(), torch.tensor(w))
                    )
    return rows, counts


def train(a):
    marks, _ = models("1M")
    states = torch.load(
        a.previous / f"s{a.seed}/1M-n1000000/weights.pt", weights_only=True
    )
    rows, counts = data(a, marks)
    stats = {"corpus": dict(counts), "arms": {}}
    for arm in rows:
        marks.load_state_dict(states[0])
        x, y, w = (
            torch.cat([s[i] if i != 2 else s[2] / s[2].sum() for s in rows[arm]])
            for i in range(3)
        )
        opt = torch.optim.AdamW(marks.parameters(), lr=0.00015)
        gen = torch.Generator().manual_seed(667)
        # Equal updates, batch size, and expected state weight across both objectives.
        draws = torch.multinomial(w, 256 * 384, replacement=True, generator=gen)
        losses = []
        for ix in draws.split(256):
            z = marks.choice(x[ix]).flatten()
            loss = binary_cross_entropy_with_logits(z, y[ix])
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(float(loss.detach()))
        torch.save(marks.state_dict(), a.out / (arm + ".pt"))
        stats["arms"][arm] = {
            "nodes": len(x),
            "states": len(rows[arm]),
            "loss_by_64": [
                np.mean(losses[i : i + 64]) for i in range(0, len(losses), 64)
            ],
        }
    (a.out / "training.json").write_text(json.dumps(stats) + "\n")


@torch.no_grad()
def evaluate(a):
    nets = {}
    for arm in ("frozen", "single", "multi"):
        marks, _ = models("1M")
        marks.load_state_dict(
            torch.load(
                a.previous / f"s{a.seed}/1M-n1000000/weights.pt", weights_only=True
            )[0]
            if arm == "frozen"
            else torch.load(a.out / (arm + ".pt"), weights_only=True)
        )
        nets[arm] = marks.eval()
    results = []
    for case in CASES:
        for m, r, g in snapshots(a, case, "teacher"):
            for arm, net in nets.items():
                rng = np.random.default_rng(573 + r)
                seen = set()
                for n in range(1, 129):
                    c = net.draw(m, rng, Counter())
                    if c in g:
                        seen.add(c)
                    if n in (1, 4, 16, 64, 128):
                        results.append(
                            {
                                "case": case,
                                "run": r,
                                "arm": arm,
                                "draws": n,
                                "known": len(g),
                                "hits": len(seen),
                                "ops": sum(g[c] for c in seen),
                            }
                        )
        print(case, "evaluated", flush=True)
    (a.out / "recall.json").write_text(json.dumps(results) + "\n")


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--seed", type=int, default=243)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    train(a)
    evaluate(a)
