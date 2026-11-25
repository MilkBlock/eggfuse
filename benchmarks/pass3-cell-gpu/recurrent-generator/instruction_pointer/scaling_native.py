"""Costed independent scaling controls on CCP v0.1; all menus are built from static receipt contracts."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import torch

from discrete_cells import Memory, load_enc
from discrete_rollout import Policy
from discrete_study import load
from entry_closure import Rules
from latent_cell_flow import ZERO, Published
from latent_egg_higher import bake
from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from scaling_bake import module, recursive_named, save
from transaction_native import execute


def menus(contract, enc, d, mode, excluded, cap):
    if mode == "prim":
        return {}
    rules = Rules(contract)
    if d.name.startswith("scale-"):
        template = read(d / "layouts.json")[0]
        steps = [
            (
                rid,
                list(rules.inputs[rid]),
                {int(pc): v["table"] for pc, v in rules.rules[rid]["outputs"].items()},
            )
            for rid, _, _ in template
        ]
        if mode in ("flat", "root", "recursive"):
            _, body, _ = module(steps, mode == "recursive")
            return {body[0][0]: body}
        out = {}
        i = 0
        while i < len(steps):
            length = min(6, len(steps) - i)
            while length > 1:
                ports, body, _ = module(steps[i : i + length])
                if ports == steps[i][1]:
                    out[body[0][0]] = body
                    break
                length -= 1
            i += length
        return out
    small = bake(contract, enc, excluded)
    if mode == "small":
        return small
    if mode in ("wide", "wide-recursive"):
        small = {r: small.get(r, rules.root(r)) for r, roles in enumerate(rules.inputs) if roles}
    # Preserve original root identities and external interface. At compile time select
    # one available named producer per new slot; guards remain verifier obligations.
    out = {}
    for root, initial in small.items():
        body = list(initial)
        used = {s[0] for s in body}
        last = {t: (-1, j) for j, t in enumerate(rules.inputs[root])}

        def publish(i, rid):
            for pc, v in rules.rules[rid]["outputs"].items():
                last[v["table"]] = (i, int(pc))

        for i, (rid, _, _) in enumerate(body):
            publish(i, rid)
        while len(body) < cap:
            ready = (
                r
                for r, tabs in enumerate(rules.inputs)
                if r not in used
                and tabs
                and all(t in last for t in tabs)
                and any(last[t][0] >= 0 for t in tabs)
            )
            r = next(ready, None)
            if r is None:
                break
            i = len(body)
            body.append((r, i, [last[t] for t in rules.inputs[r]]))
            used.add(r)
            publish(i, r)
        if len(body) > 1:
            out[root] = recursive_named(body) if mode in ("recursive", "wide-recursive") else body
    return out


class Measured(Policy):
    first_run = None
    one_job = False

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        if hasattr(self, "schedule_log"):
            self.schedule_log.append((frame["run"], [r for r, _ in frame["rules"]]))
        if getattr(self.m, "audit_routes", False):
            for rid, _ in frame["rules"]:
                if rid in self.m.menu:
                    stats[f"scheduled_root/{rid}"] += 1
        if self.first_run is None:
            self.first_run = frame["run"]
        if self.one_job and frame["run"] != self.first_run:
            # Controlled contract: a single incoming job can issue drafts on its entry Run.
            # Later publications may resume only work the network already specified.
            self.arm = "noop"
        return super().run_snapshot(frame, pub, rd, model, txn, stats, deadline)

    def issue(self, items, txn, stats):
        from discrete_draft import Local

        for item in items:
            stats["generated_external_bindings"] += sum(not isinstance(p, Local) for p in item.cell.refs)
            stats["generated_local_bindings"] += sum(isinstance(p, Local) for p in item.cell.refs)
        return super().issue(items, txn, stats)

    def send(self, items, txn, stats):
        rows = super().send(items, txn, stats)
        if len(items) <= txn.capacity:
            for item, row in zip(items, rows, strict=True):
                if item.cell.higher:
                    if getattr(self.m, "audit_routes", False):
                        stats[f"issued_root/{item.cell.rule}"] += 1
                    n = len(self.m.menu[item.cell.rule])
                    stats[f"selected/{n}"] += 1
                    if row[1] == 0:
                        stats[f"bound/{n}"] += 1
        return rows

    def resume_programs(self, frame, pub, txn, stats):
        t = perf_counter()
        if getattr(self, "count_suffix_scan", False):
            for unit, _, owners, _ in self.waiting:
                stats["suffix_wire_inspections"] += sum(len(s[2]) for s in unit[len(owners) :])
        previous = self.waiting if getattr(self, "count_suffix_scan", False) else ()
        super().resume_programs(frame, pub, txn, stats)
        for unit, _, owners, _ in previous:
            if len(owners) == len(unit):
                stats[f"completed/{len(unit)}"] += 1
        stats["continuation_seconds"] += perf_counter() - t


@torch.no_grad()
def run(a, case):
    d = folder(a.root, case)
    begin = perf_counter()
    prog = read(d / "program.json")
    enc, scorer = load_enc(prog, a.actor)
    contract = json.loads(subprocess.check_output([binary(a.root), "receipt-contract", d / "program.json"]))
    excluded = set(read(Path("run-recall/parameterized-deep-ripsat/catalog.json"))["structural_keys"])
    encoder_seconds = perf_counter() - begin
    begin = perf_counter()
    marks, nets = load(type("Weights", (), {"out": a.weights}))
    weight_load = perf_counter() - begin
    held = set(read(a.weights / "fit.json")["signatures"])
    modes = a.modes
    layouts = {}
    analyses = {}
    for mode in modes:
        begin = perf_counter()
        base = {"A": "prim", "B": "wide", "C": "wide", "old-scale": "flat", "owned-scale": "flat"}.get(
            mode, mode
        )
        if mode in ("common-topo", "common-trace"):
            from region_bake import linked

            trace = linked(prog, read(a.trace_menu))
            topo = menus(contract, enc, d, "wide", excluded, a.cap)
            use = trace if mode == "common-trace" else topo
            menu = {r: use[r] for r in sorted(trace.keys() & topo.keys())}
        elif mode in ("D", "E"):
            from region_bake import linked

            menu = linked(prog, read(a.trace_menu))
        else:
            menu = menus(contract, enc, d, base, excluded, a.cap)
        bake_seconds = perf_counter() - begin
        t = perf_counter()
        m = Memory(enc, contract, menu, scorer)
        encode = perf_counter() - t
        sigs = [enc.cat.int_bake.key(u) for u in menu.values()]
        if mode not in ("D", "E", "common-trace") and held.intersection(sigs):
            raise ValueError("training overlap")
        analyses[mode] = dict(
            bake_seconds=bake_seconds,
            structure_seconds=encode,
            encoder_seconds=encoder_seconds,
            sizes=dict(Counter(map(len, menu.values()))),
            external_arities=dict(Counter(len(u[0][2]) for u in menu.values())),
            past_catalog_overlap=len(excluded.intersection(sigs)),
            signatures=sigs,
            editor_training_overlap=len(held.intersection(sigs)),
        )
        if case.startswith("scale-") and len(menu) == 1:
            code = next(iter(m.codes.values()))
            analyses[mode]["code"] = code.tolist()
        if mode == "root":
            m.codes = {r: enc.graphs[r] for r in menu}
        layouts[mode] = m
    prefix = case + "-" + a.label
    dest = a.out / "runs"
    dest.mkdir(parents=True, exist_ok=True)
    save(dest / (prefix + ".catalog.json"), analyses)
    with TemporaryDirectory(dir=a.out) as temp:
        work = Path(temp)
        p = work / "gold.json"
        target = Target(prog, snapshot(a.root, d, "reference", "-", None, p)[0])
        initial = target.match(snapshot(a.root, d, "reference", "-", 0, p)[0])
        for b in range(a.repeats):
            pairs = [(mode, method) for mode in modes for method in a.methods]
            for mode, method in pairs if b % 2 == 0 else reversed(pairs):
                outfile = dest / f"{prefix}.{b}.{mode}.{method}.json"
                m = layouts[mode]
                m.audit_routes = a.profile
                m.pub = Published(enc)
                m.rows.clear()
                m.index.clear()
                m.options.clear()
                m.last = None
                m.receipt = ZERO
                seed = a.seed if not a.vary else a.seed + b
                cls = Measured
                if mode in ("C", "E", "owned-scale"):
                    from region_owner import Ownership

                    cls = Ownership
                pol = cls(m, marks, nets, method, 4 if method == "empty" else 1, seed, a.pages)
                if getattr(a, "save_issued", False):
                    pol.schedule_log = []
                pol.one_job = a.one_job
                pol.count_suffix_scan = a.profile
                forward_counts = Counter()

                def hook(name):
                    def count(module, inputs, output):
                        forward_counts[name] += 1

                    return count

                monitored = {
                    "mark": marks.choice,
                    "editor": nets["editor" if method == "supervised-empty" else "flow"],
                    "pointer_state": enc.actor.next_read,
                    "value": enc.actor.dynamic,
                    "age": enc.actor.age,
                }
                handles = (
                    [module.register_forward_hook(hook(k)) for k, module in monitored.items()]
                    if a.profile
                    else []
                )
                try:
                    result = execute(a.root, case, study=pol, series=temp, seconds=a.seconds)
                finally:
                    if hasattr(m, "forced_owned"):
                        del m.forced_owned
                    for h in handles:
                        h.remove()
                if a.profile:
                    result["forward_counts"] = forward_counts
                run_dir = work / (case + "-stream-multi")
                if getattr(a, "save_issued", False):
                    audit_dir = a.out / "signed"
                    audit_dir.mkdir(exist_ok=True)
                    save(
                        audit_dir / outfile.name,
                        dict(schedule=pol.schedule_log, tape=read(run_dir / "issued.json")),
                    )
                state = read(run_dir / "state.json")
                gold = sorted(target.match(state) - initial)
                paid = result["paid"]
                w = result["work"]
                effective = result["signed_ops"]
                cold = (
                    result["runtime_setup_seconds"]
                    + result["wall"]
                    + encoder_seconds
                    + analyses[mode]["bake_seconds"]
                    + analyses[mode]["structure_seconds"]
                )
                result.update(
                    policy_load_seconds=weight_load,
                    deployment_wall=cold + weight_load,
                    deployment_eps=effective / (cold + weight_load),
                    covered=len(gold),
                    reference=len(target.gold) - len(initial),
                    coverage_sha=hashlib.sha256(json.dumps(gold).encode()).hexdigest(),
                    cold=cold,
                    cold_eps=effective / cold,
                    case=case,
                    mode=mode,
                    method=method,
                    seed=seed,
                    block=b,
                    facts_per_paid=len(gold) / max(1, paid),
                    untriggered_rate=result["verdicts"].get("untriggered_rule", 0) / max(1, paid),
                    policy_forwards=w.get("address_forward_calls", 0) + w.get("edit_forward_calls", 0),
                    encoder_seconds=encoder_seconds,
                    bake_seconds=analyses[mode]["bake_seconds"],
                    structure_seconds=analyses[mode]["structure_seconds"],
                )
                if case.startswith("scale-"):
                    ref = read(d / "reference-state.json")
                    truth = {
                        (r["table"], tuple(v["value"] for v in r["values"] if "value" in v))
                        for r in ref["rows"]
                    }
                    actual = {
                        (r["table"], tuple(v["value"] for v in r["values"] if "value" in v))
                        for r in state["rows"]
                    }
                    if not actual <= truth:
                        raise ValueError("controlled semantic mismatch")
                    result["all_expected_values"] = actual == truth
                trace = result.pop("trace")
                if getattr(a, "save_trace", False):
                    with outfile.with_suffix(".jsonl").open("w") as log:
                        for frame in trace:
                            log.write(json.dumps(frame, separators=(",", ":")) + "\n")
                save(outfile, result)
    print(case, a.label, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for n in ("root", "out", "actor", "weights"):
        p.add_argument(n, type=Path)
    p.add_argument("cases", nargs="+")
    p.add_argument("--modes", nargs="+", default=["prim", "small", "flat", "root", "recursive"])
    p.add_argument("--methods", nargs="+", default=["empty", "supervised-empty"])
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--seed", type=int, default=536)
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--cap", type=int, default=256)
    p.add_argument("--seconds", type=int, default=300)
    p.add_argument("--trace-menu", type=Path)
    p.add_argument("--vary", action="store_true")
    p.add_argument("--label", default="pair")
    p.add_argument("--profile", action="store_true")
    p.add_argument("--save-trace", action="store_true")
    p.add_argument("--save-issued", action="store_true")
    p.add_argument("--one-job", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    for case in a.cases:
        run(a, case)
