"""Offline same-publication correct-Recipe intervention. All proposals get native replies."""

import csv
import hashlib
import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from binding_egg import unpack
from binding_model import collate, tensor
from binding_packets import public_view
from ccp_v01 import Client
from cell_kv_runtime import Instances
from cell_kv_world import World
from cell_transaction import STATUS
from competition_egg import egg
from completion_context import native, read
from credit_scale_buffer import submit
from discrete_cells import from_q
from discrete_draft import Cell
from head_joint_egg import parent_policy
from head_joint_index import prepare
from multirule_oracle import fork
from partner_index import noise
from partner_index_worlds import args, frozen
from query_environment import conditioned
from rule_publication import read_rule_frame
from selected_cell_model import typed_distribution
from selective_kernel import pack
from variable_completion import directory, network


def flat(n, w, m, tid, prefix):
    rid = w.layouts[tid][0][0]
    nodes, codes, _ = n.cache
    h = (m["ctx"] + codes[tid]).tanh()
    for ix in prefix:
        h = n.actor.next_read(m["ext"][ix], h)
    q = n.actor.query(h + nodes[w.cat.inputs["generated", rid][len(prefix)]])
    logits = (m["keys"][m["group"]] + m["ek"]) @ q / math.sqrt(q.numel())
    return typed_distribution(logits, m["tables"], w.roles[rid][len(prefix)])


def diagnostic(
    a, d, w, n, s, old, oldmem, model, case, rid, tape, prefix, archive, work
):
    r = s["run"]
    assert rid in s["menu"] and (not s["check_dirty"] or s["rule_state"][rid][1])
    exact = native(
        a, d, "replay", archive / "accepted.json", r - 1, "--audit-next-proofs"
    )
    gold = [from_q(q) for q in exact if q["rule"] == rid]
    rng = np.random.default_rng([113, r, rid])
    rng.shuffle(gold)
    gold = gold[:32]
    path = work / f"probe-{case}.json"
    gains, _ = fork(a, d, path, tape, prefix, r, gold)
    gold = [c for c, g in zip(gold, gains, strict=True) if g > 0]
    m = n.state(w, s)
    arity = len(w.roles[rid])
    z = public_view(oldmem, w.prog, key=(rid, False))
    assert all(
        set(refs) == {p[0] for p in s["ports"] if p[3] == table}
        for refs, table in zip(z["addrs"], w.roles[rid], strict=True)
    )
    rows = []
    for arm in ("KV", "sparse", "flat"):
        start = perf_counter()
        rng = np.random.default_rng([113, r, rid])
        uniform = rng.random((1, 16, arity), dtype=np.float32)
        stats = Counter()
        witness = []
        routes = []
        if arm == "sparse":
            chosen = old(z, tensor(uniform), rng, stats)[0].cpu().tolist()
            cells = [
                Cell(rid, tuple(z["addrs"][j][i] for j, i in enumerate(row)))
                for row in chosen
            ]
            z = dict(z, banks=[dict(b, last=-1) for b in z["banks"]])
            if stats["index_slots"]:
                data = pack([z])
                prior, edges = prepare(model, data)
            for c in gold[:4]:
                ix = [z["addrs"][j].index(ref) for j, ref in enumerate(c.refs)]
                if stats["index_slots"]:
                    mass = [float(prior[0, ix[0]])]
                    u = noise(rng, 2048, arity)
                    for j, (par, _) in enumerate(data[1], 1):
                        given = torch.full(
                            (1, 2048), ix[par], device=prior.device, dtype=torch.long
                        )
                        hit = edges[j - 1].draw(given, u[:, :, j, 0]) == ix[j]
                        mass.append(float(hit.float().mean()))
                else:
                    p, _ = model.local.base(
                        collate([z]), teacher=tensor(np.array([[ix]], np.int64))
                    )
                    mass = [float(v[0, 0, i].exp()) for v, i in zip(p, ix, strict=True)]
                witness.append(mass)
        else:
            distributions = {}
            correction = torch.tensor(
                [len(g) for g in m["siblings"]], dtype=torch.float64
            ).log()[m["group"]]

            def prob(ix, distributions=distributions, arm=arm, correction=correction):
                if ix not in distributions:
                    lp = (
                        n.address(w, m, rid, ix)
                        if arm == "KV"
                        else flat(n, w, m, rid, ix)
                    )
                    if arm == "flat":
                        reconstructed = (lp.double() - correction).softmax(0)
                        current = n.address(w, m, rid, ix).double().exp()
                        torch.testing.assert_close(
                            reconstructed, current, rtol=3e-5, atol=2e-6
                        )
                    p = lp.double().exp().numpy()
                    distributions[ix] = p / p.sum()
                return distributions[ix]

            cells = []
            for u in uniform[0]:
                ix = ()
                for v in u:
                    ix += (int(np.searchsorted(prob(ix).cumsum(), v, side="right")),)
                cells.append(Cell(rid, tuple(m["refs"][i] for i in ix)))
            for c in gold[:4]:
                ix = tuple(m["pos"][ref] for ref in c.refs)
                witness.append([prob(ix[:j])[i] for j, i in enumerate(ix)])
                route = []
                for j, i in enumerate(ix):
                    prefix_ix = ix[:j]
                    p = prob(prefix_ix)
                    owner_mass = float(
                        p[m["group"].numpy() == int(m["group"][i])].sum()
                    )
                    alternatives = np.flatnonzero(
                        m["tables"].numpy() == w.roles[rid][j]
                    )
                    features = m["ek"][alternatives]
                    rec = {
                        "owner": owner_mass,
                        "port_given_owner": float(p[i]) / owner_mass
                        if owner_mass
                        else None,
                        "key_ties": int((features == m["ek"][i]).all(1).sum()),
                        "rank": 1 + int((p > p[i]).sum()),
                    }
                    if j:
                        others = [
                            k
                            for k in np.flatnonzero(
                                m["tables"].numpy() == w.roles[rid][j - 1]
                            )
                            if k != ix[j - 1]
                        ]
                        if others:
                            swapped = prob(ix[: j - 1] + (int(others[0]),))
                            rec.update(
                                p_after_swap=float(swapped[i]),
                                distribution_l1=float(np.abs(swapped - p).sum()),
                            )
                    route.append(rec)
                routes.append(route)
            stats["distributions_including_probes"] = len(distributions)
        elapsed = perf_counter() - start
        gains, verdict = fork(a, d, path, tape, prefix, r, cells)
        rows.append(
            dict(
                case=case,
                run=r,
                rule=rid,
                arity=arity,
                arm=arm,
                domains=list(map(len, z["addrs"])),
                witness=witness,
                routes=routes,
                witness_refs=[c.refs for c in gold[:4]],
                positive_witnesses=len(gold),
                stats=stats,
                seconds_with_probes=elapsed,
                paid=len(cells),
                productive=sum(x > 0 for x in gains),
                ops=sum(gains),
                **verdict,
            )
        )
    return rows


def run(a, case):
    work = directory(a)
    base = Path(os.environ["ARTIFACT_ROOT"]) / "multi-association"
    archive = base / case / "audit-0"
    tape = read(archive / "accepted.json")
    slots = defaultdict(list)
    for q in read(archive / "slots.json"):
        if q["uid"] is not None:
            slots[q["run"]].append(q)
    rules = defaultdict(list)
    for row in csv.DictReader((base / "oracle.csv").open()):
        if row["case"] == case and int(row["arity"]):
            rules[int(row["run"])].append(int(row["rule"]))
    d = a.data / case
    ir, _ = egg(a, case)
    n = network(a, 71)
    w = World(ir, n.actor, entry_table=None, sides="")
    n.prepare(w)
    model = frozen(a, a.seeds[0])
    old = parent_policy(model, "joint")
    observer = archive / "observer.jsonl"
    oldmem = conditioned(a, d, observer)
    mem = Instances(w, True)
    rows = []
    digest = hashlib.sha256((d / "program.json").read_bytes()).hexdigest()
    cmd = [
        a.runtime_binary,
        "online-ccp-v0.1",
        d / "program.json",
        "-",
        "audit",
        "--address-seed",
        str(tape["address_seed"]),
    ]
    with observer.open() as states, subprocess.Popen(cmd, stdin=-1, stdout=-1) as proc:
        client = Client(proc, 32, digest)
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f)
                f["rule_state"], f["check_dirty"] = read_rule_frame(states, f)
                if f.get("final_publication"):
                    continue
                oldmem.update(f)
                mem.update(f)
                r = client.run = f["run"]
                client.epoch = f["epoch"]
                if r in rules:
                    s = mem.snapshot(w, f)
                    prefix = [q for q in tape["requests"] if q["run"] < r]
                    for rid in rules[r]:
                        rows.extend(
                            diagnostic(
                                a,
                                d,
                                w,
                                n,
                                s,
                                old,
                                oldmem,
                                model,
                                case,
                                rid,
                                tape,
                                prefix,
                                archive,
                                work,
                            )
                        )
                    print(case, r, len(rows), flush=True)
                cells = [
                    Cell(q["rule"], tuple(map(tuple, q["refs"]))) for q in slots[r]
                ]
                replies = submit(client, cells, 32)
                for c, rep, q in zip(cells, replies, slots[r], strict=True):
                    assert (rep[0], STATUS[rep[1]]) == (q["uid"], q["status"])
                    mem.acknowledge(client, c.rule, c.refs, rep)
                    if not rep[1]:
                        mem.begin(rep[0], c.rule, c.refs)
                client.seal()
            assert proc.wait() == 0
        finally:
            client.close()
            oldmem.close_observer()
            if proc.poll() is None:
                proc.kill()
    (work / f"binding-{case}.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
