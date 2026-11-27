"""Frozen-weight, fixed-schedule native EggCC experiments."""

import json
from functools import wraps
import os
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from continuous_stream import Stream
from discrete_reference import Reference
from foundation_egg_catalogue import install
from joint_cell_corpus import write_rows
from joint_cell_live import PageIds, UniformDecoder, classify
from joint_cell_train import fitted
from partner_index_worlds import args
from prefix_attention import attach
from region_bake import linked
from transaction_native import execute
from trigger_execution import ExecutionTrace
from variable_binding_audit import flat


def setup(a, case):
    ir, align = egg(a, case)
    net = fitted(a, case, "sweep", 71)
    w = World(ir, net.actor, entry_table=None, sides="")
    donor = json.loads(
        (Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json").read_text()
    )
    install(w, linked(w.prog, donor), "multi")
    return net, w, align


def instrument(n, arm):
    times = Counter()
    calls = Counter()

    def wrap(name, func):
        @wraps(func)
        def measured(*args, **kw):
            start = perf_counter()
            out = func(*args, **kw)
            times[name] += perf_counter() - start
            calls[name] += 1
            if name == "base_address":
                calls["candidate_rows"] += len(args[1]["refs"])
            return out

        return measured

    # Install the base read first so the trained prefix relation remains active.
    def flat_read(w, m, t, p):
        if not m["refs"]:
            return None
        lp = flat(n, w, m, t, p)
        if arm == "flat" or lp is None:
            return lp
        if "owner_cardinality_log" not in m:
            m["owner_cardinality_log"] = (
                torch.bincount(m["group"]).to(lp).log()[m["group"]]
            )
        return (lp - m["owner_cardinality_log"]).log_softmax(0)

    base = flat_read if arm in ("flat", "exact") else type(n).address.__get__(n)
    if arm == "exact":
        n.grouped_training_reduction = True
    n.address = wrap("base_address", base)
    attach(n)
    for name in (
        "address",
        "variant_prob",
        "structure",
        "instance_embedding",
        "template_readout",
        "receipt_vectors",
        "read_interface",
        "state",
    ):
        setattr(n, name, wrap(name, getattr(n, name)))
    return times, calls


def run_native(a, w, align, pol, seed, cap):
    trace = ExecutionTrace()
    ids = PageIds()
    res = native(
        a,
        w,
        policy=pol,
        seed=seed,
        slots=6,
        submit_pages=2,
        receipt_log=ids,
        receipt_memory=True,
        rule_state=True,
        execution_trace=trace,
        paid_limit=cap,
        reference=align,
    )
    tally, rows = classify(ids.pages, trace.entries)
    names = {(r["tid"], tuple(r["refs"])) for r in rows if r["effective_ops"]}
    productive = {r["uid"] for r in rows if r["effective_ops"]}
    realized = sum(
        any(ref[0] in productive for ref in r["refs"])
        for r in rows
        if r["effective_ops"]
    )
    return (
        dict(
            res,
            repeat=tally,
            productive_names=len(names),
            productive_entries=len(productive),
            downstream_productive_entries=realized,
            higher_ops=sum(r["effective_ops"] for r in trace.higher.values()),
            profile=dict(pol.time),
            counts=dict(pol.count),
        ),
        rows,
        trace.higher,
    )


class CappedReference(Reference):
    def __init__(self, cap):
        super().__init__(original_order=True)
        self.cap = cap

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        self.run_request_cap = min(6, self.cap - txn.paid)
        if self.run_request_cap > 0:
            super().run_snapshot(frame, pub, rd, model, txn, stats, deadline)


def reference(a, case, align, seed, cap):
    with TemporaryDirectory() as tmp:
        start = perf_counter()
        policy = CappedReference(cap)
        setup_time = perf_counter() - start
        r = execute(
            a.data,
            case,
            study=policy,
            series=tmp,
            seconds=600,
            runtime_binary=a.runtime_binary,
            address_seed=seed * 11 + 513,
            capacity=64,
        )
        assert r["termination"] == "schedule_end" and r["paid"] <= cap
        actual, goal = align(
            json.loads(
                (Path(tmp) / (case + "-stream-multi") / "state.json").read_text()
            )
        )
        assert not actual - goal
        work = Path(tmp) / (case + "-stream-multi")
        tape = json.loads((work / "issued.json").read_text())
        replay = json.loads(
            subprocess.check_output(
                [
                    a.runtime_binary,
                    "replay",
                    a.data / case / "program.json",
                    work / "issued.json",
                    "audit",
                    str(r["runs"]),
                    "--ept-origins",
                ]
            )
        )
        assert replay["state_sha"] == r["state_sha"]
        effects = dict(replay["ept"]["origins"])
        assert (
            sum(effects.get(q["token"], 0) for q in tape["requests"]) == r["signed_ops"]
        )
        good = [q for q in tape["requests"] if effects.get(q["token"], 0)]
        names = {
            (
                q["rule"],
                tuple(
                    (p["address"]["token"], p["address"]["op"], p["version"])
                    for p in q["parents"]
                ),
            )
            for q in good
        }
        producers = {q["token"] for q in good}
        r.update(
            productive_names=len(names),
            productive_entries=len(good),
            downstream_productive_entries=sum(
                any(p["address"]["token"] in producers for p in q["parents"])
                for q in good
            ),
        )
        r.pop("trace")
        wall = r["wall"] + r["runtime_setup_seconds"] + setup_time
        return dict(
            r,
            wall=wall,
            eps=r["signed_ops"] / wall,
            ops=r["signed_ops"],
            covered=len(actual),
            reference=len(goal),
            coverage=len(actual) / len(goal),
            facts=sorted(actual),
            graph=r["state_sha"],
        )


def output(a):
    d = a.out / "continuous-cell-stream"
    d.mkdir(exist_ok=True)
    return d


def run(a, case):
    d = output(a)
    for seed in map(int, os.getenv("CS_SEEDS", "193 307").split()):
        for budget in os.getenv("CS_CAPS", "16 32 64 128 256").split():
            cap = None if budget == "full" else int(budget)
            for arm in os.getenv("CS_ARMS", "A B C random").split():
                name = f"{case}-{budget}-{seed}-{arm}" + os.getenv("CS_REP", "")
                dest = d / (name + ".json")
                if dest.exists():
                    continue
                if arm == "history":
                    row = reference(a, case, egg(a, case)[1], seed, cap or 10**9)
                else:
                    net, w, align = setup(a, case)
                    times, calls = instrument(net, arm)
                    pol = Stream(
                        UniformDecoder() if arm in ("random", "iid") else net,
                        arm if arm in ("B", "C", "iid") else "A",
                    )
                    row, events, higher = run_native(a, w, align, pol, seed, cap)
                    write_rows(d / (name + ".pkl.gz"), (events, higher))
                    row.update(
                        network_times=times,
                        network_calls=calls,
                        parameters=sum(p.numel() for p in net.parameters()),
                        ce_parameters=sum(
                            p.numel() for p in net.parameters() if p.requires_grad
                        ),
                    )
                dest.write_text(
                    json.dumps(dict(row, arm=arm, case=case, seed=seed, budget=budget))
                )
                print(
                    name, row["covered"], row["ops"], round(row["wall"], 2), flush=True
                )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
