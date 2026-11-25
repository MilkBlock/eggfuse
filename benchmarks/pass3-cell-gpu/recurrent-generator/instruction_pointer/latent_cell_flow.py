"""Stage B: frozen Recipe graph codes and publication deltas at native fork boundaries."""

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import torch
from torch import nn

from actor import rotate, row_features
from recursive_train import read
from ripsat_policy import CellScorer, GraphBank
from rule_read import load_actor

WIDTH = 32
TRAIN = ("sum", "sum-roll", "grammar-benefit-fork-17118")
VALID = "dot"
TEST = ("fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119")
ZERO = torch.zeros(WIDTH)


class Frozen:
    def __init__(self, program, actor, scorer):
        self.actor = actor
        self.cat = actor.catalog_type(program, integer_parameters=True)
        self.nodes = actor.template_graph(self.cat)
        self.types = self.nodes[[self.cat.roots["initial", i] for i in range(len(self.cat.tables))]]
        rules = range(len(program["recipe"]["rules"]))
        layouts = [[(r, 0, [(-1, i) for i in range(len(self.cat.inputs["generated", r]))])] for r in rules]
        self.graphs = GraphBank(layouts, self.cat, self.nodes).encode(scorer)

    def ports(self, rows):
        if not rows:
            return torch.empty(0, WIDTH)
        tables = torch.tensor([r["table"] for r in rows])
        versions = torch.tensor([r["version"] for r in rows])
        status = torch.tensor([[math.log1p(r["version"]) / 8, float(r["forwarded"])] for r in rows])
        values = self.actor.dynamic(row_features([tuple(r["hashes"]) for r in rows], WIDTH, "cpu"))
        return (rotate(self.types[tables] + values, versions) + self.actor.age(status)).tanh()

    def token(self, q, live):
        refs = [(p["address"]["token"], p["address"]["op"]) for p in q["parents"]]
        features = torch.stack([live[a][1] if a in live else ZERO for a in refs]) if refs else ZERO[None]
        # Encode the network's explicit references, including the *requested* version.
        # No test of equality, current version or candidate validity is an input.
        ids = [tuple(int(x) % (1 << 64) for x in (*a, p["version"])) for a, p in zip(refs, q["parents"])]
        if refs:
            features = features + self.actor.dynamic(row_features(ids, WIDTH, "cpu"))
        return torch.cat(
            [
                self.graphs[q["rule"]],
                rotate(features, torch.arange(len(features))).sum(0) / math.sqrt(len(features)),
            ]
        )


def address(a):
    return a["token"], a["op"]


class Published:
    """Update the confirmed projection using only real published replacements and retirements."""

    def __init__(self, encoder):
        self.encoder = encoder
        self.live = {}
        self.total = ZERO.double().clone()
        self.encodings = 0

    def change(self, frame, commit):
        delta = torch.zeros_like(self.total)
        touched = {}
        for a in frame["retired"]:
            ref = address(a)
            if ref not in touched:
                delta -= self.live[ref][1]
            touched[ref] = None
        updates = frame["updates"]
        vectors = self.encoder.ports([r for _, r in updates])
        self.encodings += len(vectors)
        for (a, r), vec in zip(updates, vectors, strict=True):
            ref = address(a)
            previous = touched[ref] if ref in touched else self.live.get(ref)
            if previous is not None:
                delta -= previous[1]
            delta += vec
            touched[ref] = (r, vec)
        if commit:
            for ref, item in touched.items():
                if item is None:
                    self.live.pop(ref, None)
                else:
                    self.live[ref] = item
            self.total += delta
        return delta.float()


class Flow(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(WIDTH * 7 + 3, 96), nn.SiLU(), nn.Linear(96, WIDTH))

    def forward(self, z, pending, action, h, mode):
        return self.net(
            torch.cat((torch.asinh(z / 16), pending, action, abs(action - pending), h.log1p(), mode), dim=-1)
        )


def dataset(encoder, memory, forks):
    forks = {row["run"]: row for row in map(json.loads, forks.open())}
    confirmed = Published(encoder)
    states = []
    results = []
    exact = Counter()

    def add(run, kind, z, p, t, delta, h=1):
        results.append((run, kind, z, p, t, h, delta))

    blank = torch.zeros(2 * WIDTH)
    with memory.open() as src:
        for line in src:
            frame = json.loads(line)
            confirmed.change(frame, True)
            z = confirmed.total.float()
            states.append((frame["run"], z))
            fork = forks.get(frame["run"])
            if not fork:
                continue
            emb = {key: encoder.token(fork[key], confirmed.live) for key in ("a", "b", "bad")}
            traces = fork["cases"]
            deltas = {key: confirmed.change(case["frame"], False) for key, case in traces.items()}
            background = sum(
                (encoder.token(q, confirmed.live) for q in fork.get("background", [])), blank.clone()
            )
            # Absolute publication change with T issued, and marginal change holding a
            # previously issued prefix fixed. No post-publication state enters the input.
            for name, prev, key, current in [
                ("a", None, "a", "a"),
                ("b", None, "b", "b"),
                ("bad", None, "bad", "bad"),
                ("repeat", "a", "a", "aa"),
                ("other", "a", "b", "ab"),
                ("reverse", "b", "a", "ba"),
            ]:
                pending = background + (emb[prev] if prev else blank)
                prefix = prev or "empty"
                add(frame["run"], name, z, pending, emb[key], deltas[current] - deltas[prefix])
            for key in ("a", "b", "bad"):
                add(frame["run"], "absolute_" + key, z, background, emb[key], deltas[key])
            exact["native_repeat_duplicates"] += (
                traces["aa"]["counts"]["duplicates"] - traces["a"]["counts"]["duplicates"]
            )
            for reason, n in traces["bad"]["counts"]["rejected"].items():
                exact["invalid_" + reason] += n - traces["empty"]["counts"]["rejected"].get(reason, 0)
    for i, (run, z) in enumerate(states):
        for h in (1, 4, 16):
            if i + h < len(states):
                add(run, "future", z, blank, blank, states[i + h][1] - z, h)
    return results, dict(exact), len(states)


def tensors(rows):
    return (
        torch.stack([r[2] for r in rows]),
        torch.stack([r[3] for r in rows]),
        torch.stack([r[4] for r in rows]),
        torch.tensor([[r[5]] for r in rows]).float(),
        torch.tensor([[r[1] == "future", r[1].startswith("absolute_")] for r in rows]).float(),
        torch.stack([r[6] for r in rows]),
    )


def report(model, ds, mean, token_only):
    out = {}
    preds = {}
    for name, rows in ds.items():
        z, p, a, h, mode, y = tensors(rows)
        if token_only:
            z, p = torch.zeros_like(z), torch.zeros_like(p)
        pred = model(z, p, a, h, mode).detach()
        preds[name] = pred
        record = {}
        for kind in (
            "marginal",
            "absolute",
            "first",
            "repeat",
            "other",
            "bad",
            "future_1",
            "future_4",
            "future_16",
        ):
            pick = []
            for i, r in enumerate(rows):
                k = r[1]
                if (
                    (kind == "marginal" and k not in ("future",) and not k.startswith("absolute"))
                    or (kind == "absolute" and k.startswith("absolute"))
                    or (kind == "first" and k in ("a", "b"))
                    or (kind == "other" and k in ("other", "reverse"))
                    or (kind == k)
                    or (k == "future" and kind == f"future_{r[5]}")
                ):
                    pick.append(i)
            if pick:
                target = y[pick]
                record[kind] = dict(
                    n=len(pick),
                    mse=(pred[pick] - target).square().mean().item(),
                    zero_mse=target.square().mean().item(),
                    train_mean_mse=(mean - target).square().mean().item(),
                    nonzero=int((target.norm(dim=1) > 1e-5).sum()),
                )
        groups = defaultdict(dict)
        for i, (r, k, *_) in enumerate(rows):
            if k in ("other", "repeat"):
                groups[r][k] = i
        pairs = [
            (g["other"], g["repeat"])
            for g in groups.values()
            if y[g["other"]].norm() > 1e-5 and y[g["repeat"]].norm() < 1e-5
        ]
        record["paired_correct"] = sum(int(pred[i].norm() > pred[j].norm()) for i, j in pairs)
        record["paired_total"] = len(pairs)
        out[name] = record
    return out


def fit(ds, token_only, seed):
    torch.manual_seed(seed)
    model = Flow()
    opt = torch.optim.AdamW(model.parameters(), lr=0.002)
    rows = sum((ds[k] for k in TRAIN), [])
    x = tensors(rows)
    z, p, a, h, m, y = x
    if token_only:
        z, p = torch.zeros_like(z), torch.zeros_like(p)
    gen = torch.Generator().manual_seed(seed + 1)
    pools = [torch.where(m[:, 0].bool())[0], torch.where(m[:, 1].bool())[0], torch.where(m.sum(1) == 0)[0]]
    best = None
    for epoch in range(1, 81):
        ix = torch.cat([s[torch.randint(len(s), (256,), generator=gen)] for s in pools])
        for batch in ix[torch.randperm(len(ix), generator=gen)].split(96):
            pred = model(z[batch], p[batch], a[batch], h[batch], m[batch])
            # Equalize large schedule intervals without changing the target coordinates.
            loss = ((pred - y[batch]).square().mean(1) / (1 + y[batch].square().mean(1))).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        if epoch % 5 == 0:
            with torch.no_grad():
                val = report(model, {VALID: ds[VALID]}, ZERO, token_only)[VALID]["marginal"]["mse"]
            if best is None or val < best[0]:
                best = (val, epoch, {k: v.detach().clone() for k, v in model.state_dict().items()})
    model.load_state_dict(best[2])
    return model, best[1]


def main():
    ap = argparse.ArgumentParser()
    for n in ("data", "grammars", "store", "rollout", "actor"):
        ap.add_argument(n, type=Path)
    args = ap.parse_args()
    torch.set_num_threads(1)
    actor = load_actor(args.actor, True).eval()
    scorer = CellScorer(WIDTH).eval()
    ck = Path("run-recall/parameterized-deep-ripsat/event-gnn.pt")
    scorer.load_state_dict(torch.load(ck, weights_only=True)["model"])
    ds = {}
    meta = {}
    for name in (*TRAIN, VALID, *TEST):
        program = name.replace("-roll", "")
        d = (
            args.data / "recursive-agent" / program
            if program in ("sum", "dot")
            else (args.grammars if name.startswith("grammar") else args.data) / program
        )
        mem = args.rollout / "sum-native-memory.jsonl" if name.endswith("-roll") else d / "memory.jsonl"
        with torch.no_grad():
            ds[name], native, frames = dataset(
                Frozen(read(d / "program.json"), actor, scorer), mem, args.store / (name + ".jsonl")
            )
        meta[name] = dict(native=native, frames=frames, rows=len(ds[name]))
    mean = torch.stack(
        [r[-1] for k in TRAIN for r in ds[k] if r[1] in ("a", "b", "other", "reverse", "repeat", "bad")]
    ).mean(0)
    result = dict(
        data=meta,
        train=TRAIN,
        validation=VALID,
        tests=TEST,
        actor_sha=hashlib.sha256(args.actor.read_bytes()).hexdigest(),
        gnn_sha=hashlib.sha256(ck.read_bytes()).hexdigest(),
        fits={},
    )
    for token_only in (True, False):
        for seed in (137, 293, 431):
            model, epoch = fit(ds, token_only, seed)
            k = ("token" if token_only else "state") + str(seed)
            result["fits"][k] = dict(epoch=epoch, metrics=report(model, ds, mean, token_only))
            if k == "state137":
                torch.save(model.state_dict(), args.store / "state137.pt")
                with torch.no_grad():
                    groups = defaultdict(dict)
                    for sample in ds[VALID]:
                        groups[sample[0]][sample[1]] = sample
                    ratios = []
                    for g in groups.values():
                        if "other" not in g or g["other"][-1].norm() < 1e-5:
                            continue
                        _, _, z, p, t, _, _ = g["other"]

                        def predict(z, p, t):
                            return model(z[None], p[None], t[None], torch.ones(1, 1), torch.zeros(1, 2))[0]

                        none = torch.zeros_like(p)
                        after = z + predict(z, none, g["a"][4])
                        ratios.append(
                            float(predict(after, p, t).norm() / predict(z, none, t).norm().clamp_min(1e-8))
                        )
                    result["validation_ratio"] = min([1.0, *ratios]) if ratios else 0.0
                    result["validation_ratio_positive_pairs"] = len(ratios)
    (args.store / "prediction.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
