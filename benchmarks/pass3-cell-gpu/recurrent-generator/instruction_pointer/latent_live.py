"""Bounded, independent CCP experiment with frozen structural decoding and blind named reads."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import torch

from entry_wiring import terminal_codes
from event_addresses import Directory
from event_templates import BranchNet, Node, TemplateTree
from latent_cell_flow import WIDTH, ZERO, Flow, Frozen, Published
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from ripsat_policy import CellScorer
from rule_read import load_actor
from transaction_native import execute


class WiredTree(TemplateTree):
    def __init__(self, rd, graphs):
        groups = defaultdict(list)
        for r, roles in enumerate(rd.iface.roles):
            for i, (table, _) in enumerate(roles):
                groups[rd.tabs[table]].append((r, i))
            if not roles:
                groups[-1].append((r, -1))
        self.roots = {}
        self.minimum = {}
        for t, labels in groups.items():
            codes = np.stack([terminal_codes(graphs[r : r + 1], j)[0] for r, j in labels])
            node = Node(labels, codes)
            positions = dict(zip(labels, codes))

            def install(n):
                # The existing B binary decoder sees a real GNN code at each node.
                values = np.stack([positions[k] for k in sorted(n.labels)])
                n.code = values[np.argmin(((values - values.mean(0)) ** 2).sum(1))]
                for child in n.children:
                    install(child)

            install(node)
            self.roots[t] = node


class Live:
    def __init__(self, enc, flow, arm, ratio):
        self.enc = enc
        self.flow = flow
        self.arm = arm
        self.ratio = ratio
        self.confirmed = Published(enc)
        self.template = BranchNet().eval()
        self.template.load_state_dict(torch.load("run-recall/entry-wiring/wired.pt", weights_only=True))
        self.cuts = read(Path("run-recall/cell-events/template-fit.json"))["cuts"]
        self.mem = None
        self.keys = {}
        self.deferred = defaultdict(list)

    def bank(self, rd, t, stats):
        v = rd.versions[t]
        if t not in self.keys or self.keys[t][0] != v:
            refs = list(rd.live[t])
            keys = (
                torch.stack([self.confirmed.live[a][1] for a in refs]) if refs else ZERO.new_empty((0, WIDTH))
            )
            self.keys[t] = v, refs, keys
            stats["typed_bank_rows_rebuilt"] += len(refs)
        return self.keys[t][1:]

    def displacement(self, z, p, t, stats):
        tick = perf_counter()
        value = self.flow(z[None], p[None], t[None], torch.ones(1, 1), torch.zeros(1, 2))[0]
        stats["flow_seconds"] += perf_counter() - tick
        stats["flow_evaluations"] += 1
        return value

    def provisional(self, batch, stats):
        if not batch or self.arm not in ("serial", "Cdecode"):
            return None
        r, refs, _ = batch[0]
        q = dict(rule=r, parents=[dict(address=dict(token=t, op=o), version=v) for t, o, v in refs])
        token = self.enc.token(q, self.confirmed.live)
        change = self.displacement(self.confirmed.total.float(), torch.zeros_like(token), token, stats)
        return change if self.arm == "Cdecode" else torch.zeros_like(change)

    def flush(self, batch, txn, stats, run):
        if not batch:
            return
        ops = []
        refs = []
        z = self.confirmed.total.float()
        simulated = z
        pending = torch.zeros(2 * WIDTH)
        for i, (rule, parents, already_deferred) in enumerate(batch):
            if self.arm in ("B", "C"):
                q = dict(
                    rule=rule, parents=[dict(address=dict(token=t, op=o), version=v) for t, o, v in parents]
                )
                tok = self.enc.token(q, self.confirmed.live)
                independent = self.displacement(z, torch.zeros_like(pending), tok, stats)
                predicted = self.displacement(simulated, pending, tok, stats) if ops else independent
                if (
                    self.arm == "C"
                    and ops
                    and not already_deferred
                    and predicted.norm() < self.ratio * independent.norm()
                ):
                    self.deferred[rule].append((rule, parents, True))
                    stats["deferred"] += 1
                    continue
                if self.arm == "C":
                    simulated = simulated + predicted
                    pending = pending + tok
            key = (rule, tuple(parents))
            stats["same_run_repeated_signed"] += int(key in self.signed)
            self.signed.add(key)
            refs.extend([(*a, -1) for a in parents])
            ops.append((0, 0, rule, -1, len(refs)))
        response = txn.collect(
            txn.enqueue(np.asarray(ops, np.int64), np.asarray(refs, np.int64).reshape(-1, 4), 0)
        )
        stats["responses_observed"] += len(response.rows)
        # The transaction is settled. Confirmed port state changes only on publication.

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        tick = perf_counter()
        rows, _, retired, _ = pub
        self.confirmed.change(
            dict(
                retired=[dict(token=int(t), op=int(o)) for t, o in retired],
                updates=[
                    (dict(token=int(r[0]), op=int(r[1])), rd.store.visible[int(r[0]), int(r[1])])
                    for r in rows
                ],
            ),
            True,
        )
        stats["state_update_seconds"] += perf_counter() - tick
        if hasattr(self, "resume_programs"):
            self.resume_programs(frame, pub, txn, stats)
        if self.mem is None:
            self.mem = Directory(rd, stats)
            self.tree = WiredTree(rd, self.enc.graphs)
        rules = dict(frame["rules"])
        batch = []
        self.signed = set()
        self.searched = set()
        for r in rules:
            for item in self.deferred.pop(r, []):
                batch.append(item)
                if len(batch) == 2:
                    self.flush(batch, txn, stats, frame["run"])
                    batch = []
        seen = set()
        for r, anchor, ix in self.tree.emit(self.mem, rules, self.template, self.cuts, stats):
            if perf_counter() >= deadline:
                raise TimeoutError()
            chunks = ([i] for i in ix) if self.arm in ("serial", "Cdecode") else (ix,)
            for ix in chunks:
                roles = self.mem.roles[r]
                n = len(ix)
                parents = [[] for _ in ix]
                if roles:
                    src = self.mem.bank(roles[anchor])
                    addrs = [src.ports[i] for i in ix]
                    h = self.enc.graphs[r].expand(n, -1)
                    context = self.provisional(batch, stats)
                    if context is not None:
                        h = h + context.tanh()
                    versions = tuple(rd.versions[t] for t in roles)
                    for address in addrs:
                        audit = (r, anchor, address, versions)
                        stats["same_run_repeated_root_search"] += int(audit in self.searched)
                        self.searched.add(audit)
                    chosen = {anchor: addrs}
                    for j in self.mem.order(r, anchor):
                        if j != anchor:
                            typed, keys = self.bank(rd, roles[j], stats)
                            if not typed:
                                break
                            scores = self.enc.actor.query(h) @ keys.T
                            if hasattr(self, "search_history"):
                                for index in range(n):
                                    prefix = tuple(
                                        (
                                            slot,
                                            chosen[slot][index],
                                            self.confirmed.live[chosen[slot][index]][0]["version"],
                                        )
                                        for slot in chosen
                                    )
                                    audit = (r, j, prefix, rd.versions[roles[j]])
                                    if audit in self.search_history:
                                        stats["revisited_identical_pointer_positions"] += len(typed)
                                    self.search_history.add(audit)
                            stats["pointer_positions_scored"] += scores.numel()
                            chosen[j] = [typed[i] for i in scores.argmax(1).tolist()]
                        k = torch.stack([self.confirmed.live[a][1] for a in chosen[j]])
                        h = self.enc.actor.next_read(
                            k + self.enc.nodes[self.enc.cat.inputs["generated", r][j]], h
                        )
                    if len(chosen) != len(roles):
                        continue
                    for j in range(len(roles)):
                        for out, a in zip(parents, chosen[j]):
                            out.append((*a, int(rd.store.visible[a]["version"])))
                for refs in parents:
                    # Read-only audit counter. The generator never consults this set.
                    key = (r, tuple(refs))
                    stats["repeated_complete_proposals"] += int(key in seen)
                    seen.add(key)
                    stats["complete_proposals"] += 1
                    batch.append((r, refs, False))
                    if len(batch) == 2:
                        self.flush(batch, txn, stats, frame["run"])
                        batch = []
        self.flush(batch, txn, stats, frame["run"])
        stats["unresolved_deferred"] = sum(map(len, self.deferred.values()))
        stats["port_encodings"] = self.confirmed.encodings


def main():
    p = argparse.ArgumentParser()
    for s in ("data", "store", "actor"):
        p.add_argument(s, type=Path)
    p.add_argument("case")
    p.add_argument("arms", nargs="+", choices=["A", "B", "C", "serial", "Cdecode"])
    p.add_argument("--ratio", type=float, required=True)
    p.add_argument("--block", type=int, required=True)
    p.add_argument("--search-audit", action="store_true")
    args = p.parse_args()
    torch.set_num_threads(1)
    torch.set_grad_enabled(False)
    d = folder(args.data, args.case)
    with TemporaryDirectory(dir=args.store) as tmp:
        path = Path(tmp) / "ref.json"
        tg = Target(read(d / "program.json"), snapshot(args.data, d, "reference", "-", None, path)[0])
        initial = tg.match(snapshot(args.data, d, "reference", "-", 0, path)[0])
        for arm in args.arms:
            tick = perf_counter()
            actor = load_actor(args.actor, True)
            scorer = CellScorer(WIDTH).eval()
            scorer.load_state_dict(
                torch.load("run-recall/parameterized-deep-ripsat/event-gnn.pt", weights_only=True)["model"]
            )
            enc = Frozen(read(d / "program.json"), actor, scorer)
            flow = Flow().eval()
            flow.load_state_dict(torch.load(args.store / "state137.pt", weights_only=True))
            policy = Live(enc, flow, arm, args.ratio)
            if args.search_audit:
                policy.search_history = set()
            setup = perf_counter() - tick
            row = execute(args.data, args.case, study=policy, seconds=180, series=tmp)
            state = read(Path(tmp) / (args.case + "-stream-multi") / "state.json")
            covered = sorted(tg.match(state) - initial)
            row["covered"] = len(covered)
            row["covered_sha"] = hashlib.sha256(json.dumps(covered).encode()).hexdigest()
            row["reference"] = len(tg.gold) - len(initial)
            row["setup"] = setup
            row["end_to_end_eps"] = row["signed_ops"] / (row["wall"] + setup + row["runtime_setup_seconds"])
            row.pop("trace", None)
            (
                args.store / f"{'audit' if args.search_audit else 'live'}-{args.case}-{arm}-{args.block}.json"
            ).write_text(json.dumps(row, indent=2) + "\n")


if __name__ == "__main__":
    main()
