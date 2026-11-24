"""Offline native verdicts, effective-operation attribution and deletion forks."""

import argparse
import json
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import torch
from torch.nn import functional as F
from generation_targets import OutcomeNet
from protocol_experiment import dump
from recursive_train import binary, folder, read
from recursive_agent import Reader, Compose
from recursive_coverage import Target, snapshot
from stream_guard import GuardStream, Study

TRAIN = (
    "loopfact",
    "grammar-17118",
    "grammar-17119",
    "grammar-stride2-17118",
    "grammar-benefit-fork-17120",
)


def ledger(root, d, tape, *flags):
    return json.loads(
        subprocess.check_output(
            [binary(root), "replay", d / "program.json", tape, "time", *flags]
        )
    )


def sample_case(root, case, backbone, seed, tmp):
    rng = random.Random(seed)
    d = folder(root, case)
    tape = read(d / "tape.json")
    origin = dict(ledger(root, d, d / "tape.json", "--ept-origins")["ept"]["origins"])
    rd = Reader(read(d / "program.json"), root, rename_seed=seed)
    rows = tape["requests"]
    uses = Counter()
    selected = defaultdict(list)
    for q in rows:
        uses.update({p["address"]["token"] for p in q["parents"]})
    choices = [q for q in rows if q["parents"]]
    for q in rng.sample(choices, min(520, len(choices))):
        selected[q["run"]].append(q)
    features = []
    probes = []
    originals = {}
    for f in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(f)
        streams = {}
        for q in selected[f["run"]]:
            rid = q["rule"]
            if rid not in streams:
                s = GuardStream(
                    rd, backbone, rid, dict(f["rules"])[rid], Counter(), study=Study()
                )
                s.prepare()
                streams[rid] = s, [{k: i for i, k in enumerate(g)} for g in s.roles]
            s, lookup = streams[rid]
            src = [q["parents"][i] for i in s.order]
            addrs = [
                (rd.store.alias(p["address"]["token"]), p["address"]["op"]) for p in src
            ]
            positions = [lookup[i][a] for i, a in enumerate(addrs)]
            paths = [positions]
            for j, k in enumerate(addrs):
                tab, h, codes = rd.index.rows[k]
                peers = list(rd.index.buckets[tab, 0, codes[0]])
                aliases = [a for a in peers if a != k and rd.index.rows[a][1] == h]
                for alt in [
                    *rng.sample(aliases, min(2, len(aliases))),
                    rng.choice(peers),
                    rng.choice(s.roles[j]),
                ]:
                    if alt != k:
                        v = positions.copy()
                        v[j] = lookup[j][alt]
                        paths.append(v)
            paths = torch.tensor(list(dict.fromkeys(map(tuple, paths))))
            h = backbone.start(rd.meta(rid)).expand(len(paths), -1)
            for j in range(len(src)):
                score, h = s.logits(h, j, paths[:, : j + 1])
            xx = OutcomeNet.inputs(s, h, score, j, paths)
            for k, path in enumerate(paths):
                parents = [None] * len(src)
                for j, i in enumerate(path.tolist()):
                    t, op = s.roles[j][i]
                    parents[s.order[j]] = dict(
                        address=dict(token=rd.store.original[t], op=op),
                        version=rd.store.visible[t, op]["version"],
                    )
                idx = len(probes)
                if not k:
                    originals[idx] = q["token"]
                probes.append(
                    dict(run=q["run"], rule=rid, parents=parents, token=idx + 1)
                )
                features.append(xx[k])
    probe = tmp / "probe.json"
    dump(probe, {**tape, "requests": probes})
    rep = ledger(root, d, d / "tape.json", "--recall", probe)
    assert not rep["unused_recall"] and len(rep["recall_verdicts"]) == len(probes)
    truth = {i - 1: (winner, why) for _, i, winner, why in rep["recall_verdicts"]}
    assert all(truth[i][0] == t for i, t in originals.items())
    alternatives = defaultdict(list)
    bytoken = {q["token"]: q for q in rows}
    for i, (owner, reason) in truth.items():
        if (
            owner in bytoken
            and probes[i]["run"] == bytoken[owner]["run"]
            and probes[i]["parents"] != bytoken[owner]["parents"]
        ):
            alternatives[owner].append(probes[i]["parents"])
    # Fixed-point loss under a one-action deletion, retaining all later
    # certificates. A verified alternative can be substituted under its own fork.
    state = tmp / "state.json"
    ref = snapshot(root, d, "reference", "-", None, state)[0]
    target = Target(read(d / "program.json"), ref)
    baseline = len(target.match(ref))
    forks = {}
    owners = sorted(set(originals.values()))
    groups = [
        [t for t in owners if key(t)]
        for key in (
            lambda t: t in alternatives,
            lambda t: uses[t] > 0,
            lambda t: uses[t] == 0,
        )
    ]
    for t in dict.fromkeys(t for g in groups for t in rng.sample(g, min(len(g), 12))):
        effects = {}
        for variant in ("delete", "substitute") if t in alternatives else ("delete",):
            changed = [
                q if q["token"] != t else dict(q, parents=alternatives[t][0])
                for q in rows
                if q["token"] != t or variant == "substitute"
            ]
            dump(probe, {**tape, "requests": changed})
            run = subprocess.run(
                [
                    binary(root),
                    "replay",
                    d / "program.json",
                    probe,
                    "time",
                    "--export",
                    state,
                ],
                capture_output=True,
            )
            if run.returncode:
                effects[variant + "_error"] = run.stderr.decode()[-250:]
                continue
            effects[variant] = baseline - len(target.match(read(state)))
        forks[t] = effects
    labels = []
    for i in range(len(probes)):
        owner, why = truth[i]
        valid = owner is not None or why == "off_reference"
        current = owner in bytoken and bytoken[owner]["run"] == probes[i]["run"]
        lost = forks.get(owner, {})
        # Conditional novelty of this semantic binding on the teacher trajectory.
        # Alternative certificates for the same binding share its label.
        novelty = float(current and origin.get(owner, 0) > 0)
        demand = float(uses[owner] > 0) if current else 0.0
        labels.append(
            [
                valid,
                novelty,
                demand,
                min(1, max(0, lost.get("delete", 0)) / 8),
                current and "delete" in lost,
            ]
        )
    return (
        torch.stack(features),
        torch.tensor(labels, dtype=torch.float),
        dict(
            probes=len(probes),
            unique_alternatives=len(alternatives),
            labels=torch.tensor(labels, dtype=torch.float).sum(0).tolist(),
            forks=forks,
        ),
    )


def fit(root, out):
    torch.manual_seed(37409)
    torch.set_num_threads(1)
    base = Compose().eval()
    base.load_state_dict(
        torch.load(root / "recursive-agent/multi.pt", weights_only=True)
    )
    parts = []
    info = {}
    with torch.no_grad(), TemporaryDirectory() as tmp:
        for i, c in enumerate(TRAIN):
            x, y, info[c] = sample_case(root, c, base, 39031 + i, Path(tmp))
            parts.append((x, y))
            print(c, info[c]["probes"], flush=True)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    x, y = [torch.cat(g).to(dev) for g in zip(*parts)]
    model = OutcomeNet().to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=0.002)
    causal = torch.where(y[:, 4] > 0)[0]
    for _ in range(480):
        ix = torch.randint(len(x), (192,), device=dev)
        j = causal[torch.randint(len(causal), (32,), device=dev)]
        scores = model(x[ix])
        loss = F.binary_cross_entropy_with_logits(
            scores, y[ix, :3]
        ) + F.binary_cross_entropy_with_logits(model(x[j])[:, 2], y[j, 3])
        opt.zero_grad()
        loss.backward()
        opt.step()
    torch.save(model.cpu().eval().state_dict(), out / "outcomes.pt")
    dump(out / "supervision.json", dict(device=dev, seed=37409, programs=info))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    fit(a.root, a.out)
