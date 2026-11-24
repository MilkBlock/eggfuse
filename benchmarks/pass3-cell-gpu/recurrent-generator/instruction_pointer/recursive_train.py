"""Train shared recurrent address selection on validated trajectories and offline experts."""

import argparse
import json
import random
import subprocess
from collections import defaultdict
from pathlib import Path

import torch
from torch.nn import functional as F

from recursive_agent import Compose, Reader

TRAIN = (
    "fact",
    "loopfact",
    "sum-divisors",
    "jacobi",
    *(f"grammar-{s}" for s in range(17118, 17122)),
)


def folder(root, case):
    return (
        root / case
        if case in ("fact", "loopfact", "sum-divisors")
        else root / "recursive-agent" / case
    )


def binary(root):
    return root / "unified-scale/build/release/examples/cell_token_replay"


def read(path):
    return json.loads(path.read_bytes())


def keys(p):
    return tuple((a["address"]["token"], a["address"]["op"]) for a in p["parents"])


def native_labels(root, d, tape, probes, out):
    t = read(tape)
    probe = out / "probes.json"
    for i, q in enumerate(probes, 1):
        q["token"] = i
    probe.write_text(json.dumps({**t, "requests": probes}))
    rep = json.loads(
        subprocess.check_output(
            [
                binary(root),
                "replay",
                d / "program.json",
                tape,
                "audit",
                "--recall",
                probe,
            ]
        )
    )
    assert not rep["unused_recall"] and len(rep["recall_verdicts"]) == len(probes)
    return [
        probes[i - 1]
        for _, i, w, reason in rep["recall_verdicts"]
        if w is not None or reason == "off_reference"
    ], rep["state_sha"]


def samples(root, d, frames, labels, seed):
    rd = Reader(read(d / "program.json"), root, rename_seed=seed)
    by = defaultdict(list)
    for q in labels:
        if q["parents"]:
            by[q["run"]].append(q)
    rng = random.Random(seed)
    output = []
    with frames.open() as stream:
        for f in map(json.loads, stream):
            rd.advance(f)
            packets = by.get(f["run"], ())
            if not packets:
                continue
            groups = defaultdict(set)
            for q in packets:
                r = q["rule"]
                seq = tuple(keys(q)[j] for j in rd.order(r))
                groups[r].add(seq)
            wm = dict(f["rules"])
            for r, paths in groups.items():
                paths = sorted(paths)
                for path in rng.sample(paths, min(3, len(paths))):
                    steps = []
                    for j, k in enumerate(path):

                        def alias(addr):
                            return rd.store.alias(addr[0]), addr[1]

                        raw_prefix = path[:j]
                        seq = tuple(alias(a) for a in raw_prefix)
                        k = alias(k)
                        pos = {alias(x[j]) for x in paths if x[:j] == raw_prefix}
                        domain, x = rd.read(r, seq, wm[r], 0, cap=20, force=[k])
                        order = list(range(len(domain)))
                        rng.shuffle(order)
                        ix = order.index(domain.index(k))
                        steps.append(
                            (
                                x[order],
                                torch.tensor([domain[i] in pos for i in order]),
                                ix,
                            )
                        )
                    output.append((rd.meta(r), steps))
    return output


def substitutions(d, frames, subset, rng):
    # Offline label proposals only. Submit substitutions to the native verifier;
    # never put an equality join on the actor inference path.
    groups = defaultdict(list)
    for p in subset:
        groups[p["run"]].append(p)
    live = {}
    probes = []
    for f in map(json.loads, frames.open()):
        for a in f["retired"]:
            live.pop((a["token"], a["op"]))
        for a, row in f["updates"]:
            live[a["token"], a["op"]] = row
        if f["run"] not in groups:
            continue
        equiv = defaultdict(list)
        for k, row in live.items():
            equiv[row["table"], tuple(row["hashes"])].append(k)
        for q in groups[f["run"]]:
            for j, k in enumerate(keys(q)):
                row = live[k]
                vs = [a for a in equiv[row["table"], tuple(row["hashes"])] if a != k]
                if not vs:
                    continue
                t, op = rng.choice(vs)
                parents = list(q["parents"])
                parents[j] = dict(
                    address=dict(token=t, op=op), version=live[t, op]["version"]
                )
                probes.append(dict(q, parents=parents))
    return probes


def rule_samples(d, root):
    rd = Reader(read(d / "program.json"), root)
    goals = defaultdict(set)
    for q in read(d / "tape.json")["requests"]:
        goals[q["run"]].add(q["rule"])
    rows = []
    last = {}
    for f in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(f)
        for r, wm in f["rules"]:
            rows.append(
                (rd.rule_state(r, wm, f["run"], last.get(r, 0)), r in goals[f["run"]])
            )
        for r in goals[f["run"]]:
            last[r] = f["run"]
    return rows


def fit(root, phase):
    out = root / "recursive-agent"
    torch.manual_seed(7631)
    data_rng = random.Random(7631)
    rng = random.Random(7631)
    model = Compose()
    if phase == "dagger":
        model.load_state_dict(torch.load(out / "teacher.pt", weights_only=True))
    allrows = []
    records = {}
    rule_rows = []
    for case in TRAIN:
        d = folder(root, case)
        work = out / ("fit-" + case)
        work.mkdir(exist_ok=True)
        rule_file = work / "activations.pt"
        if not rule_file.exists():
            torch.save(rule_samples(d, root), rule_file)
        rule_rows += torch.load(rule_file, weights_only=True)
        f = work / "samples.pt"
        # Cache the data RNG continuation independently of optimizer sampling.
        cursor = work / "sampling-state.pt"
        if not f.exists() or not cursor.exists():
            reqs = read(d / "tape.json")["requests"]
            subset = data_rng.sample(reqs, min(480, len(reqs)))
            probes = substitutions(d, d / "memory.jsonl", subset, data_rng)
            extra, sha = native_labels(root, d, d / "tape.json", probes, work)
            assert sha == read(d / "capture.json")["state_sha"]
            rows = samples(root, d, d / "memory.jsonl", subset + extra, 1703)
            torch.save((rows, len(subset), len(probes), len(extra)), f)
            torch.save(data_rng.getstate(), cursor)
        else:
            data_rng.setstate(torch.load(cursor, weights_only=True))
        rows, n, p, e = torch.load(f, weights_only=True)
        allrows += rows
        records[case] = dict(
            teacher=n, alternative_probes=p, verified=e, examples=len(rows)
        )
        if phase == "dagger":
            folder2 = out / ("own-" + case)
            extra = read(folder2 / "labels.json")
            own = samples(root, d, folder2 / "memory.jsonl", extra, 445)
            allrows += own
            records[case]["expert_examples"] = len(own)
    # Batch by varying path depth with masked candidate sets. Actual chosen port
    # states carry the gradient to earlier Compose steps.
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    optim = torch.optim.AdamW(
        model.parameters(), lr=0.003 if phase == "teacher" else 0.001
    )
    steps = 260 if phase == "teacher" else 140
    active = [v for v, y in rule_rows if y]
    silent = [v for v, y in rule_rows if not y]
    for step in range(steps):
        batch = rng.choices(allrows, k=32)
        h = model.start(torch.stack([m for m, _ in batch]).to(device))
        loss = 0.0
        terms = 0
        for j in range(max(len(p) for _, p in batch)):
            ix = [i for i, (_, p) in enumerate(batch) if len(p) > j]
            rag = [batch[i][1][j] for i in ix]
            X = torch.nn.utils.rnn.pad_sequence(
                [v for v, _, _ in rag], batch_first=True
            ).to(device)
            positive = torch.nn.utils.rnn.pad_sequence(
                [v for _, v, _ in rag], batch_first=True
            ).to(device)
            lens = torch.tensor([len(v) for v, _, _ in rag], device=device)
            mask = torch.arange(X.size(1), device=device)[None, :] < lens[:, None]
            ii = torch.tensor(ix, device=device)
            z = model.cell(
                model.encode(X.flatten(0, 1)),
                h[ii, None, :].expand(-1, X.size(1), -1).reshape(-1, h.size(1)),
            ).view(len(ix), X.size(1), -1)
            raw = model.score(z).squeeze(-1) + 2 * X[:, :, 24]
            loss += (
                raw.masked_fill(~mask, -1e4).logsumexp(1)
                - raw.masked_fill(~positive, -1e4).logsumexp(1)
            ).sum()
            # Retry utility predicts multiple verified next options at this prefix.
            loss += 0.2 * F.binary_cross_entropy_with_logits(
                model.retry(h[ii]).flatten(),
                (positive.sum(1) > 1).float(),
                reduction="sum",
            )
            h = h.index_copy(
                0,
                ii,
                z[
                    torch.arange(len(ix), device=device),
                    torch.tensor([k for _, _, k in rag], device=device),
                ],
            )
            terms += len(ix)
        features = torch.tensor(
            rng.choices(active, k=48) + rng.choices(silent, k=48), device=device
        )
        rule_loss = F.binary_cross_entropy_with_logits(
            model.activation(features).flatten(),
            torch.tensor([1.0] * 48 + [0.0] * 48, device=device),
        )
        optim.zero_grad()
        (loss / terms + rule_loss).backward()
        optim.step()
    torch.save(model.cpu().state_dict(), out / (phase + ".pt"))
    (out / (phase + "-training.json")).write_text(
        json.dumps(
            dict(device=device, steps=steps, records=records, examples=len(allrows)),
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("phase", choices=("teacher", "dagger"))
    a = p.parse_args()
    torch.set_num_threads(1)
    fit(a.root.resolve(), a.phase)
