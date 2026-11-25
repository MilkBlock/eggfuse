"""Cell-first template and parent generation on the frozen publication boundary."""

from collections import defaultdict
from time import perf_counter
import numpy as np
import torch
from cell_stream import CellStream
from event_addresses import AddressNet, Directory, PAGE, pages, ranges
from event_templates import BranchNet, TemplateTree
from higher_replacement import send
from recursive_train import read


class EventGenerator:
    def __init__(self, root, case, out, mode):
        if mode not in ("B", "C", "D"):
            raise ValueError(mode)
        self.mode = mode
        self.template = BranchNet().eval()
        self.template.load_state_dict(
            torch.load(out / "template.pt", weights_only=True)
        )
        self.cuts = read(out / "template-fit.json")["cuts"]
        self.address = AddressNet().eval()
        self.address.load_state_dict(torch.load(out / "events.pt", weights_only=True))
        self.address_cut = read(out / "calibration.json")["address"]["threshold"]
        self.memory = None
        self.waiting = defaultdict(dict)
        self.generation = {}
        self.compute = None
        if mode == "D":
            from event_computation import Computation

            self.compute = Computation(out)

    def wake(self, rules, stats):
        mem = self.memory
        for k, waiting in list(self.waiting.items()):
            r, j = k
            if r not in rules or not waiting:
                continue
            versions = tuple(
                mem.rd.versions[mem.roles[r][a]] for a in mem.order(r, j)[1:]
            )
            if self.generation.get(k) == versions:
                continue
            self.generation[k] = versions
            bank = mem.bank(mem.roles[r][j])
            old = []
            for a, v in list(waiting.items()):
                i = bank.positions.get(a)
                if i is None or bank.rows[i, 2] != v:
                    del waiting[a]
                    stats["retired_opportunities"] += 1
                elif v < rules[r]:
                    old.append(i)
            for start in range(0, len(old), PAGE):
                ix = np.array(old[start : start + PAGE], dtype=np.int64)
                stats["old_port_wakes"] += len(ix)
                yield r, j, ix, True

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        if self.memory is None:
            self.memory = Directory(rd, stats)
            self.tree = TemplateTree(rd)
        mem = self.memory
        rules = dict(frame["rules"])
        audit = getattr(self, "audit", None)
        if audit is not None and audit.run != frame["run"]:
            audit = None
        scored = {}
        higher = getattr(self, "higher", None)
        if higher is not None:
            higher.start(rd, pub, txn, rules, stats)
            higher.parent_model = model

        def emit(r, order, paths):
            refs = np.empty((len(paths), len(order), 3), np.int64)
            for k, j in enumerate(order):
                refs[:, j] = mem.bank(mem.roles[r][j]).rows[paths[:, k]]
            roots = paths[:, 0] if order else np.zeros(len(paths), dtype=np.int64)
            if order and rd.iface.rules[r]["metadata"]["seminaive"]:
                legal = (refs[:, :, 2] >= rules[r]).any(1)
                stats["old_only_paths"] += int((~legal).sum())
                refs = refs[legal]
                roots = roots[legal]
            stats["named_parent_reads"] += len(paths) * len(order)
            if len(refs):
                # Formation is the issue boundary: no subsequent tuple classifier.
                if higher is None:
                    send(txn, r, refs)
                else:
                    higher.issue(r, roots, refs, txn)
                stats["generated_proofs"] += len(refs)

        def decode(r, order, depth, paths, h, legacy):
            if perf_counter() >= deadline:
                raise TimeoutError
            if audit is not None:
                audit.prefix(mem, r, order, depth, paths)
            if depth == len(order):
                emit(r, order, paths)
                return
            dst = order[depth]
            win = mem.window(r, order[:depth], dst, paths)
            if self.compute:
                win = self.compute.address(mem, r, order, depth, paths, txn, stats, win)
            groups = win if isinstance(win, list) else [(np.arange(len(paths)), *win)]
            for ix, post, start, n in groups:
                if isinstance(win, list):
                    start, n = start[ix], n[ix]
                parents = paths[ix]
                stats["addressable_positions"] += int(n.sum())
                if legacy is not None:
                    lo = np.zeros_like(n)
                    count = n
                else:
                    pred = self.address(
                        torch.from_numpy(mem.features(r, order[:depth], parents, n))
                    ).numpy()
                    lo, hi = ranges(pred, n)
                    count = np.where(
                        (n > 0) & (pred[:, 0] >= self.address_cut), hi - lo + 1, 0
                    )
                    stats["pointer_instructions"] += len(parents)
                    stats["span_positions_issued"] += int(count.sum())
                if audit is not None:
                    audit.window(
                        mem, r, order, depth, parents, post, start, n, lo, count
                    )
                batches = pages(start + lo, count)
                if (depth + 1 == len(order) and higher is not None
                        and getattr(higher, "covered_rules", {}).get(r)):
                    batches = higher.uncovered(mem, r, order, parents, post, start + lo, count)
                for owner, pos in batches:
                    addr = pos if post is None else post[pos]
                    stats["visits"] += len(addr)
                    child = np.column_stack((parents[owner], addr))
                    z = None
                    if legacy is not None:
                        logits, z = legacy.logits(
                            h[ix[owner]], depth, torch.from_numpy(child)
                        )
                        stats["parent_candidate_scores"] += len(child)
                        if depth + 1 == len(order):
                            stats["complete_candidate_scores"] += len(child)
                        keep = logits >= 0
                        child = child[keep.numpy()]
                        z = z[keep]
                    if len(child):
                        decode(r, order, depth + 1, child, z, legacy)

        def dispatch(r, j, ix, woke):
            if perf_counter() >= deadline:
                raise TimeoutError
            order = mem.order(r, j)
            if (len(order) == 1 and higher is not None
                    and getattr(higher, "covered_rules", {}).get(r)):
                ix = higher.uncovered_events(mem, r, j, ix)
                if not len(ix):
                    return
            if higher is not None:
                higher.choose(r, j, ix, mem, woke)
            paths = ix[:, None] if order else np.empty((len(ix), 0), np.int64)
            stats["woken_templates" if woke else "generated_templates"] += len(ix)
            if not woke and len(order) > 1:
                bank = mem.bank(mem.roles[r][j])
                self.waiting[r, j].update(
                    (bank.ports[i], int(bank.rows[i, 2])) for i in ix
                )
                self.generation[r, j] = tuple(
                    rd.versions[mem.roles[r][a]] for a in order[1:]
                )
            project = getattr(higher, "project_entries", None)
            if project is not None:
                project(r, j, mem, txn)
            if audit is not None:
                audit.prefix(mem, r, order, min(1, len(order)), paths)
            if any(not len(mem.bank(mem.roles[r][a]).ports) for a in order):
                return
            h = legacy = None
            if self.mode == "B" and len(order) > 1:
                if (r, j) not in scored:
                    ptr = CellStream(
                        rd,
                        model,
                        r,
                        rules[r],
                        stats,
                        order=order,
                        role_ports=lambda t: mem.bank(t).ports,
                    )
                    ptr.prepare()
                    scored[r, j] = ptr
                legacy = scored[r, j]
                _, h = legacy.logits(
                    model.start(rd.meta(r)).expand(len(ix), -1),
                    0,
                    torch.from_numpy(paths),
                )
            decode(r, order, min(1, len(order)), paths, h, legacy)

        for r, j, ix, woke in self.wake(rules, stats):
            dispatch(r, j, ix, woke)
        for r, j, ix in self.tree.emit(mem, rules, self.template, self.cuts, stats):
            dispatch(r, j, ix, False)
        stats["live_pending"] = sum(map(len, self.waiting.values()))
        stats["peak_pending"] = max(stats["peak_pending"], stats["live_pending"])
