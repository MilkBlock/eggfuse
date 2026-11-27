"""Free complete-token draws and fixed-schedule CCP validation. Oracle is explicit and offline."""

import json
import os
from collections import Counter, defaultdict

import numpy as np
import torch

from cell_kv_runtime import native
from competition_draw import Page
from continuous_stream import Stream
from continuous_trials import instrument, setup
from foundation_world import world
from incremental_native import Ledger
from joint_cell_live import UniformDecoder
from joint_cell_sweep import complete_ce
from partner_index_worlds import args
from scaling_archive import directory
from scaling_fit import atomic
from scaling_pool import Pool


class TemperaturePage(Page):
    def __init__(self, n, w, s, temperature):
        super().__init__(n, w, s)
        self.temperature = temperature

    def transition(self, key):
        t = super().transition(key)
        if t is None or self.temperature == 1:
            return t
        p, child = t
        with np.errstate(divide="ignore"):
            scores = np.log(p) / self.temperature
        weights = np.exp(scores - scores.max())
        return weights / weights.sum(), child


class Sampling(Stream):
    def __init__(self, n, temp, unique):
        super().__init__(n, "A")
        self.temp, self.unique = temp, unique

    def generate(self, w, s, rng, slots):
        if not s["menu"]:
            return []
        page = TemperaturePage(self.net, w, s, self.temp)
        return [t for t in page.draws(rng, slots, self.unique) if t is not None]


class OfflineInactiveWindow(Sampling):
    def generate(self, w, s, rng, slots):
        if s["check_dirty"]:
            types = {p[3] for p in s["ports"]}
            roots = {w.layouts[t][0][0] for t in s["menu"]}
            constructible = [r for r in roots if all(v in types for v in w.roles[r])]
            if constructible and all(not s["rule_state"][r][1] for r in constructible):
                self.count["intervened_pages"] += 1
                self.count["withheld_slots"] += slots
                return []
        return super().generate(w, s, rng, slots)


def frozen(a, model, case="loopfact"):
    n, w, ref = setup(a, case)
    if model == "initial":
        from joint_cell_train import fitted

        n = fitted(a, "sum-divisors", "sweep", 0)
    elif model != "sweep":
        n.load_state_dict(
            torch.load(directory(a) / "fits" / (model + ".pt"), weights_only=True)
        )
    n.eval()
    return n, w, ref


def probes(a, n, pool_model=None):
    pool = Pool(a, n if pool_model is None else pool_model)
    groups = defaultdict(dict)
    for key, w, s, ts in pool.val:
        for t in ts:
            label = "higher" if t[0] >= w.primitives else f"parents_{min(3, len(t[1]))}"
            groups[label].setdefault(key, (w, s, set()))[2].add(t)
    rows = []
    for label, states in sorted(groups.items()):
        for key in sorted(states)[:24]:
            w, s, ts = states[key]
            n.prepare(w)
            n.physical = ("held", 0)
            page = Page(n, w, s)
            if "pos" not in page.m:
                page.m["pos"] = {r: i for i, r in enumerate(page.m["refs"])}
            ce = float(complete_ce(n, w, page.m, sorted(ts)))
            draws = page.draws(np.random.default_rng(307), 32, False)
            valid = [t for t in draws if t in ts]
            rows.append(
                {
                    "group": label,
                    "state": key,
                    "targets": len(ts),
                    "ce": ce,
                    "slots": 32,
                    "complete": sum(t is not None for t in draws),
                    "known_hits": len(valid),
                    "different_hits": len(set(valid)),
                }
            )
    return rows


def evaluate(a):
    d = directory(a)
    model = os.environ.get("CELL_MODEL", "sweep")
    mode = os.getenv("CELL_EVAL", "validation")
    if mode in ("outer", "timing", "intervention") and not json.loads(
        (d / "campaign.json").read_text()
    ).get("locked"):
        raise ValueError("outer execution requires a locked configuration")
    temp = float(os.getenv("CELL_TEMP", "1"))
    unique = int(os.getenv("CELL_UNIQUE", "1"))
    slots = int(os.getenv("CELL_SLOTS", "6"))
    cases = {
        "validation": ["loopfact", "foundation185510", "foundation185511"],
        "outer": ["sum-divisors"],
        "intervention": ["loopfact", "sum-divisors"],
        "inner-intervention": ["loopfact"],
        "selection": ["loopfact"],
        "timing": ["sum-divisors"],
    }[mode]
    out = d / "eval"
    out.mkdir(exist_ok=True)
    dest = out / f"{mode}-{model}-T{temp:g}-U{unique}-N{slots}.json"
    if dest.exists():
        return
    runs = []
    probes_data = []
    for case in cases:
        n, w, ref = frozen(
            a,
            "sweep" if model == "factorized-random" else model,
            case if case in ("sum-divisors", "loopfact") else "loopfact",
        )
        if case.startswith("foundation"):
            w = world(a, n.actor, int(case[10:]), True, "multi")
            ref = None
        pool_model = n
        if model == "factorized-random":
            n = UniformDecoder()
        if mode == "validation" and case == "loopfact":
            probes_data = probes(a, n, pool_model)
        if model != "factorized-random":
            instrument(n, "exact")
        for cap in map(int, os.getenv("CELL_CAPS", "16 32 64 128 256").split()):
            for draw in (193, 307):
                policy = (
                    OfflineInactiveWindow
                    if mode in ("intervention", "inner-intervention")
                    else Sampling
                )(n, temp, unique)
                trace = Ledger()
                r = native(
                    a,
                    w,
                    policy=policy,
                    seed=draw,
                    slots=slots,
                    submit_pages=2,
                    receipt_memory=True,
                    rule_state=True,
                    reference=ref,
                    execution_trace=trace,
                    paid_limit=cap,
                )
                names = {
                    (v["tid"], tuple(v["refs"]))
                    for v in trace.entries.values()
                    if v["effective_ops"] > 0
                }
                runs.append(
                    dict(
                        r,
                        case=case,
                        seed=draw,
                        cap=cap,
                        shortfall=cap - r["stats"]["paid"],
                        paid=r["stats"]["paid"],
                        productive_names=len(names),
                        statuses=dict(
                            Counter(x["status"] for x in trace.entries.values())
                        ),
                        response_sha=trace.response_digest,
                        intervention=dict(policy.count),
                    )
                )
    atomic(
        dest,
        {
            "model": model,
            "mode": mode,
            "temperature": temp,
            "unique": unique,
            "slots": slots,
            "runs": runs,
            "probes": probes_data,
        },
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        evaluate(args())
