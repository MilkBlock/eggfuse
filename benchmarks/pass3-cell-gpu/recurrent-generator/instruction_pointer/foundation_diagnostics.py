"""Offline known-evidence forks, fixed-interface native Higher, and index scaling."""

import json
from collections import Counter, defaultdict
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import torch

from binding_model import read_packet
from completion_context import read
from first_parent import records
from foundation_completion import Completion, Decision
from foundation_study import BASE, CASES, network
from multirule_higher import trial
from multirule_oracle import fork
from partner_index_worlds import args, frozen
from query_environment import conditioned
from recursive_train import folder


@torch.no_grad()
def forks(a):
    rows = []
    for case in CASES:
        d = folder(a.data, case)
        src = BASE / "corpus" / ("rollout-" + case)
        tape = read(BASE / case / "audit-0/accepted.json")
        groups = defaultdict(list)
        for x in read_packet(src / "examples.pkl"):
            if x["z"] and x["g"]:
                groups[x["run"]].append(x)
        prog = read(d / "program.json")
        m = conditioned(a, d, src / "observer")
        dec = network(a, case, "ce-evidence")
        try:
            for line in (src / "frames").open():
                f = json.loads(line)
                if f.get("final_publication"):
                    continue
                r = f["run"]
                m.update(f)
                dec.publish(m, prog, f, Counter())
                if r not in groups:
                    continue
                x = groups[r][0]
                g = x["g"][0]
                role = r % len(g)
                ref = x["z"]["addrs"][role][g[role]]
                for hint in (None, ref):
                    rng = np.random.default_rng(1651 + r)
                    stats = Counter()
                    cells = [
                        dec.finish(Decision(dec.net, rng, stats), hint=hint)[1]
                        for _ in range(8)
                    ]
                    issued = [c for c in cells if c is not None]
                    gains, verdict = fork(
                        a,
                        d,
                        a.out / "diagnostic-fork.json",
                        tape,
                        [q for q in tape["requests"] if q["run"] < r],
                        r,
                        issued,
                    )
                    rows.append(
                        dict(
                            case=case,
                            run=r,
                            anchor=hint is not None,
                            source_role=role,
                            slots=8,
                            paid=len(issued),
                            productive=sum(g > 0 for g in gains),
                            ops=sum(gains),
                            **verdict,
                        )
                    )
        finally:
            m.close_observer()
        records(a.out / "hints.csv", rows)


class Interface:
    def __init__(self, model):
        self.dec = Completion(model, "rule")
        self.cost = 0.0

    def publish(self, m, prog, frame):
        torch.mps.synchronize()
        t = perf_counter()
        self.dec.publish(m, prog, frame, Counter())
        torch.mps.synchronize()
        self.cost += perf_counter() - t

    def bind(self, rid, code):
        d = self.dec
        d.rkeys[d.rpos[rid]] = code.to(d.device)
        rng = np.random.default_rng(419)
        stats = Counter()
        torch.mps.synchronize()
        t = perf_counter()
        cells = [
            d.finish(Decision(d.net, rng, stats), fixed_rule=rid)[1] for _ in range(32)
        ]
        torch.mps.synchronize()
        return cells, d.mem.bytes(), self.cost * 1000, (perf_counter() - t) * 1000


@torch.no_grad()
def higher(a):
    (a.out / "higher").mkdir(exist_ok=True)
    model = frozen(a, a.seeds[0])
    rows = []
    for n in (6, 32, 128, 256):
        d = folder(BASE / "higher/data", f"scale-fork-{n}-2-17-jobs8")
        for block in range(3):
            rows.append(trial(a, d, model, block, Interface(model)))
        records(a.out / "higher.csv", rows)


class Fixture:
    """Standalone cost fixture with known physical sizes. No execution or accuracy claims."""

    def __init__(self, n, width, catalog):
        rng = np.random.default_rng(423)
        self.roles = [(0, 0)] * catalog
        self.ids = [(r, False) for r in range(catalog)]
        values = torch.from_numpy(rng.normal(size=(catalog + 2, 32)).astype(np.float32))
        self.vec = values
        self.enc = SimpleNamespace(
            nodes=values,
            cat=SimpleNamespace(
                inputs={("generated", r): [r, r + 1] for r in range(catalog)}
            ),
        )
        self.ctx = values[-1]
        self.pub = SimpleNamespace(live={})
        self.keys = {}
        self.up = []
        for i in range(n):
            rec = {
                "table": 0,
                "version": 1,
                "hashes": rng.integers(0, 2**63, size=width, dtype=np.uint64).tolist(),
            }
            self.pub.live[i, 0] = (rec, None)
            self.keys[i, 0] = torch.from_numpy(rng.normal(size=32).astype(np.float32))
            self.up.append(({"token": i, "op": 0}, rec))
        self.prog = {
            "recipe": {
                "rules": [
                    {
                        "interface": {
                            "rows": [
                                {
                                    "columns": [
                                        {"slot": (j + r) % width} for j in range(width)
                                    ]
                                },
                                {"columns": [{"slot": j} for j in range(width)]},
                            ]
                        }
                    }
                    for r in range(catalog)
                ]
            }
        }

    def graph(self, key):
        return self.vec[key[0]]

    def context(self):
        return self.ctx

    def key(self, ref):
        return self.keys[ref]


@torch.no_grad()
def scale(a):
    rows = []
    mdl = frozen(a, a.seeds[0])
    grid = (
        [(n, 4, 16) for n in (32, 256, 1024)]
        + [(256, f, 16) for f in (1, 8, 16)]
        + [(256, 4, c) for c in (1, 64, 256)]
    )
    for n, w, c in grid:
        m = Fixture(n, w, c)
        dec = Completion(mdl, "evidence")
        st = Counter()
        # Publish the data before the Recipe catalog is consulted.
        torch.mps.synchronize()
        t = perf_counter()
        dec.mem.publish(m, {"updates": m.up, "retired": []}, st)
        torch.mps.synchronize()
        build = perf_counter() - t
        size = dec.mem.bytes()
        original = m.ids
        m.ids = original[:1]
        dec.publish(
            m,
            {"recipe": {"rules": m.prog["recipe"]["rules"][:1]}},
            {"updates": [], "retired": []},
            st,
        )
        m.ids = original
        before = st["rows_encoded"]
        torch.mps.synchronize()
        t = perf_counter()
        dec.publish(m, m.prog, {"updates": [], "retired": []}, st)
        torch.mps.synchronize()
        static = perf_counter() - t
        assert dec.mem.bytes() == size and st["rows_encoded"] == before
        for block in range(3):
            ss = Counter()
            rng = np.random.default_rng(419 + block)
            t = perf_counter()
            dec.generate(m, 8, rng, ss)
            torch.mps.synchronize()
            rows.append(
                dict(
                    rows=n,
                    fields=w,
                    recipes=c,
                    block=block,
                    payload=size,
                    added_encodings=st["rows_encoded"] - before,
                    publication_ms=build * 1000,
                    catalog_ms=static * 1000,
                    page_ms=(perf_counter() - t) * 1000,
                    **{
                        k: ss[k]
                        for k in (
                            "scored_options",
                            "categorical_reads",
                            "row_positions",
                        )
                    },
                )
            )
        records(a.out / "scale.csv", rows)


@torch.no_grad()
def posterior(a):
    rows = []
    for case in CASES:
        for arm in ("frozen-evidence", "ce-evidence"):
            dec = network(a, case, arm)
            net = dec.net.cpu()
            for source in (case, "rollout-" + case):
                data = torch.load(
                    a.out / "data" / (source + ".pt"),
                    map_location="cpu",
                    weights_only=False,
                )
                for _, run, _, cell, paths in data:
                    if not cell.refs:
                        continue
                    joint = torch.tensor(
                        [sum(float(c.logp(net)[y]) for c, y in path) for path in paths]
                    )
                    total = joint.logsumexp(0)
                    rows.append(
                        {
                            "case": case,
                            "arm": arm,
                            "source": source,
                            "run": run,
                            "rule": cell.rule,
                            "arity": len(cell.refs),
                            "token_probability": float(total.exp()),
                            "evidence_posterior": float(
                                (joint[1:].logsumexp(0) - total).exp()
                            ),
                        }
                    )
    records(a.out / "posterior.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    {"cost": scale, "evaluate": forks, "live": higher, "cpu": posterior}[a.task](a)
