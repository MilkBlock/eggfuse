"""Held-only native interventions. Never imported by a training or rollout policy."""

import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch

from boundary_inputs import CASE
from discrete_cells import from_q
from discrete_draft import Local, plan
from discrete_editor import sampler
from recursive_train import binary, folder, read
from response_study import arguments, memory, weights
from scaling_bake import save
from version_replay import PRIOR, compile_dag, replay


def draw(models, m, draft, seed):
    net, methods = models
    xs = sampler(
        methods["flow"],
        net,
        m,
        plan(draft),
        "flow",
        4,
        np.random.default_rng(seed),
        Counter(),
    )
    return [
        [
            x.cell.rule,
            x.cell.higher,
            [
                ["local", p.owner, p.port] if isinstance(p, Local) else list(p)
                for p in x.cell.refs
            ],
        ]
        for x in xs
    ]


@torch.no_grad()
def audit(a):
    d = folder(a.data, CASE)
    tape = read(d / "tape.json")
    by = {q["token"]: q for q in tape["requests"]}
    models = weights(a, "D")
    prior = Path("run-recall/version-aware")
    goals = defaultdict(dict)
    for row in read(prior / "causes.json")["rows"]:
        goals[row["seal"]][tuple(row["address"])] = row
    result = []
    seeds = range(16)
    with TemporaryDirectory() as tmp:
        path = Path(tmp)
        for seal, ports in goals.items():
            halves = []
            for label in ("full", "omit_seal"):
                last = max(by[g["consumers"][0][0]]["run"] for g in ports.values())
                # Resume the same background script in both arms. Rejected background
                # requests in the intervention remain rejected and are never repaired.
                ledger = dict(
                    tape,
                    requests=[
                        q
                        for q in by.values()
                        if q["run"] < last and (q["run"] != seal or label == "full")
                    ],
                    repair_events=[],
                )
                save(path / "tape.json", ledger)
                native = json.loads(
                    subprocess.check_output(
                        [
                            binary(a.data),
                            "replay",
                            d / "program.json",
                            path / "tape.json",
                            "time",
                            str(last),
                            "--memory",
                            path / "memory.jsonl",
                        ]
                    )
                )
                if label == "full":
                    assert native["counts"]["accepted"] == len(ledger["requests"])
                decision = {}
                responses = {}
                plans = None
                m = memory(a, d)
                with (path / "memory.jsonl").open() as frames:
                    for f in map(json.loads, frames):
                        m.update(f)
                        if f["run"] == seal + 1:
                            for addr in ports:
                                live = m.pub.live.get(addr)
                                responses[addr] = live[0] if live else None
                            plans = [draw(models, m, [], s) for s in seeds]
                            early = set(m.ids)
                        for addr, g in ports.items():
                            target = by[g["consumers"][0][0]]
                            if f["run"] == target["run"]:
                                actual = from_q(target)
                                decision[addr] = dict(
                                    scheduled=(actual.rule, False) in m.ids_index,
                                    refs_visible=all(
                                        w[:2] in m.pub.live
                                        and m.pub.live[w[:2]][0]["version"] == w[2]
                                        for w in actual.refs
                                    ),
                                    plans=[draw(models, m, [], s) for s in seeds],
                                )
                assert responses and plans is not None
                halves.append((responses, plans, early, decision))
            for addr, g in ports.items():
                full, omit = [v[0][addr] for v in halves]
                assert full == g["observation"] and omit != full
                consumer = from_q(by[g["consumers"][0][0]])
                needed = [consumer.rule, False, [list(x) for x in consumer.refs]]
                late = [v[3].get(addr, {}) for v in halves]
                result.append(
                    dict(
                        late_scheduled=[v.get("scheduled") for v in late],
                        late_visible=[v.get("refs_visible") for v in late],
                        late_consumer=[
                            sum(needed in z for z in v.get("plans", [])) for v in late
                        ],
                        late_rule=[
                            sum(
                                any(t[0] == consumer.rule for t in z)
                                for z in v.get("plans", [])
                            )
                            for v in late
                        ],
                        seal=seal,
                        address=addr,
                        actual=[full, omit],
                        samples=len(seeds),
                        changed=sum(x != y for x, y in zip(halves[0][1], halves[1][1])),
                        target_scheduled=(consumer.rule, False) in halves[0][2],
                        generated_consumer=[
                            sum(needed in z for z in v[1]) for v in halves
                        ],
                    )
                )
    save(a.out / "revision-pairs.json", result)

    # Same paid writer accepted in both arms. Preserve native IDs for all model reads;
    # the offline reverse map is used only to identify the observation and label reports.
    bounds = next(
        r
        for r in read(PRIOR / "boundaries.json")
        if r["root"] == 1007 and r["label"] == "both_ancestries"
    )
    ex = read(prior / "expanded-1007.json")
    group = set(bounds["region"]["tokens"]) | set(ex["added"])
    causal = {(k, i): set(v) for k, i, v in ex["revision_edges"]}
    before = {int(k): set(v) for k, v in ex["writer_after_owner"].items()}
    with (d / "memory.jsonl").open() as f:
        wires = compile_dag(by.values(), map(json.loads, f))
    observations = {}
    frames = {}
    for tag in ("full_order", "ordered_causes"):
        m = memory(a, d)
        sample = {}

        def on_frame(f, rows, hashes, retired, published, reverse):
            if sample or f["final_publication"]:
                return
            updates = []
            start = 0
            for tid, pc, tab, v, forward, end in rows.tolist():
                updates.append(
                    (
                        dict(token=tid, op=pc),
                        dict(
                            table=tab,
                            version=v,
                            forwarded=bool(forward),
                            hashes=hashes[start:end].tolist(),
                        ),
                    )
                )
                start = end
            m.update(
                dict(
                    rules=f["rules"],
                    retired=[dict(token=t, op=p) for t, p in retired.tolist()],
                    accepted=published,
                    updates=updates,
                )
            )
            if 204 in [reverse.get(t) for t, _ in published.tolist()]:
                actual = next(t for t, k in reverse.items() if k == 149)
                row = m.pub.live[actual, 3][0]
                sample.update(
                    run=f["run"],
                    port=row,
                    ids=m.ids,
                    plans=[draw(models, m, [], s) for s in seeds],
                )

        args = (
            (list(by.values()), {})
            if tag == "full_order"
            else ([by[k] for k in sorted(group)], dict(causes=causal, precedes=before))
        )
        r = replay(a.data, tape, args[0], wires, tag, observer=on_frame, **args[1])
        assert r["issued"][204][1] == "accepted" and sample
        frames[tag] = m
        observations[tag] = dict(
            accepted_writer=r["issued"][204], consumer=r["issued"].get(326), **sample
        )
    assert [v["port"]["version"] for v in observations.values()] == [19, 15]
    save(a.out / "writer204.json", observations)
    swapped = []
    for label, m in frames.items():
        other = frames["full_order" if label == "ordered_causes" else "ordered_causes"]
        original = m.publication
        control = observations[label]["plans"]
        # Inference-only channel intervention: confirmed Memory, IDs, mark stream,
        # sampled uniforms, current schedule and empty draft remain exactly fixed.
        for treatment, vector in (
            ("other_publication", other.publication),
            ("mask", torch.zeros_like(original)),
        ):
            m.publication = vector
            m.refresh()
            altered = [draw(models, m, [], s) for s in seeds]
            swapped.append(
                dict(
                    environment=label,
                    treatment=treatment,
                    changed=sum(a != b for a, b in zip(control, altered)),
                    samples=len(control),
                )
            )
        m.publication = original
        m.refresh()
    save(a.out / "writer204-channel.json", swapped)


if __name__ == "__main__":
    torch.set_num_threads(1)
    audit(arguments())
