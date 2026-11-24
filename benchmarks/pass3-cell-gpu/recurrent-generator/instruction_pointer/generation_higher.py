"""Pre-issue a baked layout from its visible root boundary, using the existing native layout receiver."""

import argparse
import json
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from time import perf_counter
import torch
from torch import nn
from torch.nn import functional as F
from protocol_experiment import dump, digest
from recursive_agent import Reader, Compose
from recursive_train import read, folder, binary
from recursive_coverage import Target, snapshot
from ripsat_layout import capture, signatures
from ripsat_replay import unpack
from stream_guard import GuardStream, Study

BAKE = Path("run-recall/unified-layouts")


class Layouts:
    def __init__(self, program):
        docs = read(BAKE / "fixed.json")
        if docs["catalog"] != digest(BAKE / "catalog.json") or docs["codes"] != digest(
            BAKE / "codes.pt"
        ):
            raise ValueError("Bake artifact identity mismatch")
        mapping = {sig: i for i, sig in enumerate(signatures(program))}
        units = unpack(read(BAKE / "catalog.json"))
        codes = torch.load(BAKE / "codes.pt", weights_only=True)["codes"]
        self.units = []
        self.original = []
        self.by = defaultdict(list)
        self.index = {}
        emb = []
        for i, u in enumerate(units):
            if any(docs["signatures"][r] not in mapping for r, g, w in u):
                continue
            boundary = u[0][2]
            if tuple(boundary) != tuple((-1, j) for j in range(len(boundary))):
                continue
            if any(
                s >= len(boundary) for _, _, w in u for parent, s in w if parent < 0
            ):
                continue
            mapped = [(mapping[docs["signatures"][r]], g, w) for r, g, w in u]
            uid = len(self.units)
            self.units.append(mapped)
            self.original.append(i)
            self.index[u] = uid
            self.by[mapped[0][0]].append(uid)
            emb.append(
                torch.cat(
                    (
                        codes[i],
                        torch.tensor(
                            [
                                len(u) / 10,
                                len(boundary) / 10,
                                max(g for _, g, _ in u) / 10,
                            ]
                        ),
                    )
                )
            )
        self.codes = (
            torch.stack(emb) if emb else codes.new_empty((0, codes.shape[-1] + 3))
        )


class Recognizer(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.root = nn.Linear(28, 32)
        self.layout = nn.Linear(width, 32)
        self.score = nn.Linear(32, 1)

    def forward(self, x, code):
        return self.score((self.root(x) + self.layout(code)).tanh()).squeeze(-1)


def contexts(rd, rule, addresses):
    rows = [rd.index.keys[a].mean(0) for a in addresses]
    return torch.cat(
        (torch.stack(rows).mean(0) if rows else torch.zeros(24), rd.meta(rule))
    )


def fit(root, out, donor_dir, include=None):
    donor = read(donor_dir / "program.json")
    torch.manual_seed(40177)
    rng = random.Random(40177)
    records = []
    counts = {}
    for d in (donor_dir, folder(root, "loopfact")):
        prog = read(d / "program.json")
        cat = Layouts(prog)
        rd = Reader(prog, root, rename_seed=8711)
        refs, _, occ, _ = capture(d, donor, 10, grow_consumers=True)
        # Match the frozen layout signature numbering to the donor used by Bake.
        assert signatures(donor) == read(BAKE / "fixed.json")["signatures"]
        byrun = defaultdict(list)
        for idx, q in enumerate(refs):
            byrun[q["run"]].append((idx, q))
        hits = Counter()
        for frame in map(json.loads, (d / "memory.jsonl").open()):
            rd.advance(frame)
            for idx, q in byrun[frame["run"]]:
                menu = cat.by[q["rule"]]
                if include is not None:
                    menu = [i for i in menu if include(cat.original[i])]
                if not menu:
                    continue
                positive = {
                    cat.index[l]
                    for l, instances in occ.get(idx, {}).items()
                    if l in cat.index
                    and (include is None or include(cat.original[cat.index[l]]))
                    and any(ready and first for _, ready, first, _ in instances)
                }
                ctx = contexts(
                    rd,
                    q["rule"],
                    [
                        (rd.store.alias(p["address"]["token"]), p["address"]["op"])
                        for p in q["parents"]
                    ],
                )
                rest = sorted(set(menu) - positive)
                for uid in sorted(positive) + rng.sample(rest, min(len(rest), 12)):
                    records.append((ctx, cat.codes[uid], float(uid in positive)))
                    hits[int(uid in positive)] += 1
        counts[str(d.name)] = dict(hits)
    x, c, y = map(torch.stack, zip(*[(x, c, torch.tensor(y)) for x, c, y in records]))
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    x, c, y = x.to(dev), c.to(dev), y.to(dev)
    net = Recognizer(c.shape[1]).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=0.003)
    pos = torch.where(y > 0)[0]
    for _ in range(450):
        ix = torch.cat(
            (
                torch.randint(len(y), (96,), device=dev),
                pos[torch.randint(len(pos), (32,), device=dev)],
            )
        )
        loss = F.binary_cross_entropy_with_logits(net(x[ix], c[ix]), y[ix])
        opt.zero_grad()
        loss.backward()
        opt.step()
    torch.save(net.cpu().state_dict(), out / "higher.pt")
    dump(
        out / "higher-training.json",
        dict(
            train=counts, device=dev, catalog=digest(BAKE / "catalog.json"), seed=40177
        ),
    )


@torch.no_grad()
def run(root, out, case, arm, repeat, verified_receiver=None):
    from replacement_stream import ReplacementStream

    pending = set()
    d = folder(root, case)
    prog = read(d / "program.json")
    cat = Layouts(prog)
    rd = Reader(prog, root)
    net = Recognizer(cat.codes.shape[1]).eval()
    net.load_state_dict(torch.load(out / "higher.pt", weights_only=True))
    compose = Compose().eval()
    compose.load_state_dict(
        torch.load(root / "recursive-agent/multi.pt", weights_only=True)
    )
    policy = Study(bits=8, symmetric=True, delta_buckets=True)
    counts = Counter()
    stats = Counter()
    paid = 0
    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        layouts = tmp / "layouts.json"
        state = tmp / "state.json"
        dump(layouts, cat.units)
        target = Target(prog, snapshot(root, d, "reference", "-", None, state)[0])
        seed = target.match(snapshot(root, d, "reference", "-", 0, state)[0])
        receiver = verified_receiver or binary(root)
        cmd = [
            receiver,
            "online",
            d / "program.json",
            "-",
            "time",
            "--export",
            state,
            "--verified-layouts" if verified_receiver else "--layouts",
            layouts,
            "--ept",
        ]
        with (
            TemporaryFile() as err,
            subprocess.Popen(cmd, stdin=-1, stdout=-1, stderr=err) as p,
        ):
            start = perf_counter()
            try:
                for line in p.stdout:
                    f = json.loads(line)
                    if "role" in f:
                        if pending:
                            raise ValueError(
                                "unconfirmed preverified layout steps at shutdown"
                            )
                        break
                    certified = defaultdict(set)
                    if verified_receiver:
                        accepted = {p["token"] for p in f["accepted"]}
                        if not pending <= accepted:
                            raise ValueError("accepted layout did not commit")
                        pending.clear()
                        for token, rule, parents in f["verified_steps"]:
                            pending.add(token)
                            certified[rule].add(
                                tuple(
                                    (
                                        a["address"]["token"],
                                        a["address"]["op"],
                                        a["version"],
                                    )
                                    for a in parents
                                )
                            )
                        counts["verified_steps"] += len(pending)
                    rd.advance(f)
                    batch = []
                    scheduled = set(dict(f["rules"]))
                    for rid, wm in f["rules"]:
                        menu = (
                            [
                                i
                                for i in cat.by[rid]
                                if all(
                                    r in scheduled for r, g, w in cat.units[i] if g == 0
                                )
                            ]
                            if arm not in ("atomic", "A")
                            else []
                        )
                        if arm == "higher" and not menu:
                            continue
                        stream = ReplacementStream(
                            rd, compose, rid, wm, stats, study=policy
                        )
                        covered = (
                            stream.covered_paths(certified[rid])
                            if arm in ("C", "D")
                            else set()
                        )
                        stream.exclusions = covered if arm == "D" else set()
                        for paths in stream.path_batches("stream", 0, float("inf")):
                            if covered and (arm == "C" or not paths.shape[1]):
                                paths = stream.remove_scored(paths, covered, counts)
                            if not len(paths):
                                continue
                            selected = [None] * len(paths)
                            if menu and arm != "atomic":
                                tick = perf_counter()
                                ctx = (
                                    torch.stack(
                                        [
                                            stream.tables[j][1][paths[:, j]]
                                            for j in range(paths.shape[1])
                                        ]
                                    ).mean(0)
                                    if paths.shape[1]
                                    else torch.zeros(len(paths), 24)
                                )
                                xx = torch.cat(
                                    (ctx, rd.meta(rid).expand(len(paths), -1)), 1
                                )
                                # Vectorize over complete boundary instances and eligible templates.
                                logits = net(
                                    xx[:, None, :], cat.codes[menu][None, :, :]
                                )
                                val, col = logits.max(1)
                                selected = [
                                    menu[k] if a > 0 else None
                                    for a, k in zip(val.tolist(), col.tolist())
                                ]
                                counts["recognition_scores"] += logits.numel()
                                counts["recognition_seconds"] += perf_counter() - tick
                            refs = [
                                stream.port_refs(j)[paths[:, j]]
                                for j in sorted(
                                    range(len(stream.order)),
                                    key=stream.order.__getitem__,
                                )
                            ]
                            rows = (
                                torch.stack(refs, 1).tolist()
                                if refs
                                else [[] for _ in paths]
                            )
                            for rr, u in zip(rows, selected, strict=True):
                                if u is None and arm == "higher":
                                    continue
                                parents = [
                                    dict(address=dict(token=t, op=pc), version=v)
                                    for t, pc, v in rr
                                ]
                                paid += 1
                                req = dict(
                                    token=paid, rule=rid, run=f["run"], parents=parents
                                )
                                if u is not None:
                                    req["graph"] = dict(layout=u, boundary=parents)
                                    counts["higher_issued"] += 1
                                batch.append(req)
                    p.stdin.write(json.dumps(batch).encode() + b"\n")
                    p.stdin.flush()
                p.stdin.close()
                if p.wait() or "role" not in f:
                    err.seek(0)
                    raise RuntimeError(err.read().decode()[-600:])
            finally:
                if p.poll() is None:
                    p.kill()
        wall = perf_counter() - start
        signed = sum(f["ept"]["signed_external"]) + sum(f["ept"]["signed_internal"])
        m = dict(
            case=case,
            arm=arm,
            repeat=repeat,
            wall=wall,
            coverage=len(target.match(read(state)) - seed),
            reference=len(target.gold) - len(seed),
            paid=paid,
            signed=signed,
            ept=signed / max(1, paid),
            eps=signed / wall,
            visits=stats["visits"],
            work=dict(stats),
            generation=dict(counts),
            counts=f["counts"],
            layouts=f["layouts"],
            ledger=f["ept"],
            sha=f["state_sha"],
            verify=f["verify_seconds"],
            runs=f["runs"],
            build=digest(receiver),
        )
        dump(out / f"higher_{case}_{arm}_{repeat}.json", m)
        print(case, arm, m["coverage"], paid, f["ept"]["signed_internal"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--donor", type=Path)
    p.add_argument("--cases", nargs="*", default=[])
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--verified-receiver", type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    if a.donor:
        fit(a.root, a.out, a.donor)
    for c in a.cases:
        for i in range(a.reps):
            if a.verified_receiver:
                for arm in "ABCD" if i % 2 == 0 else "DCBA":
                    run(a.root, a.out, c, arm, i, a.verified_receiver)
                continue
            for arm in (
                ("atomic", "higher", "mixed")
                if i % 2 == 0
                else ("mixed", "higher", "atomic")
            ):
                run(a.root, a.out, c, arm, i)
