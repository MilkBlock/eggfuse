"""Condition the existing sparse decoder on the actual publication and CCP reply."""

from collections import defaultdict
from dataclasses import replace
from time import perf_counter

import torch

from discrete_cells import ZERO, Cell, Local, Memory
from region_owner import Ownership


class ResponseMemory(Memory):
    def __init__(self, enc, contract, menu, scorer, owner=True):
        super().__init__(enc, contract, menu, scorer)
        self.owner_rule = {}
        self.contract_cache = {}
        self.contract = contract
        self.open_evidence = ZERO
        self.projections = []
        for outputs in self.output_tables:
            roles = defaultdict(list)
            for pc, table in outputs.items():
                roles[table].append(pc)
            self.projections.append(
                {t: pcs[0] for t, pcs in roles.items() if len(pcs) == 1}
            )
        self.grouped = owner
        self.conditioned = True
        self.publication = ZERO
        self.outcome = ZERO

    def wire_contract(self, unit, step, slot):
        """Resolve a Recipe input at compile time. Availability is a runtime observation."""
        rid, _, wiring = unit[step]
        src, pc = wiring[slot]
        rule = self.contract["rules"][rid]
        role = rule["inputs"][slot]
        if src < 0:
            table = self.roles[unit[0][0]][pc]
            source = {"kind": "external_reference", "binding": pc}
        else:
            if src >= step:
                raise ValueError("noncausal Higher wire")
            producer = unit[src][0]
            site = self.contract["rules"][producer]["outputs"][str(pc)]
            table = site["table"]
            source = {
                "kind": site["producer"],
                "presence": site["presence"],
                "step": src,
                "pc": pc,
            }
        if table != role["table"]:
            raise ValueError("Higher input/output role mismatch")
        return {
            "source": source,
            "role": role,
            "query": rule["query_conditions"],
            "computations": rule["computations"],
            "availability": self.contract["availability"],
            "lifetime": self.contract["lifetime"],
            "unresolved_environment": "native consumer guard over actual named inputs",
        }

    def owner_contract(self, consumer, anchor):
        """A program-local specialization, selected once by the shared mark decoder."""
        if not self.grouped or isinstance(anchor, Local):
            return {}
        producer = self.owner_rule.get(anchor[0])
        if producer is None:
            return {}
        key = consumer, producer
        if key not in self.contract_cache:
            roles = self.projections[producer]
            self.contract_cache[key] = {
                i: roles[tab]
                for i, tab in enumerate(self.roles[consumer])
                if i and tab in roles
            }
        return self.contract_cache[key]

    def refresh(self):
        if not self.conditioned:
            self.state = (
                self.pub.total.float() / 16
            ).asinh().tanh() + 0.1 * self.receipt
            return
        self.state = (
            (self.pub.total.float() / 16).asinh().tanh()
            + self.publication
            + self.outcome
            + self.open_evidence
        )

    def update(self, frame):
        before = self.pub.total.clone()
        super().update(frame)
        self.publication = ((self.pub.total - before).float() / 4).asinh().tanh()
        rules = []
        for item in frame.get("accepted", ()):
            if isinstance(item, dict):
                owner, rid = item["token"], item["rule"]
            else:
                owner, rid = map(int, item)
            self.owner_rule[owner] = rid
            rules.append(self.enc.graphs[rid])
        self.outcome = torch.stack(rules).mean(0) if rules else ZERO
        self.refresh()

    def reply(self, outcomes):
        # Include the actual signed token, preserving the identity of a wrong binding.
        self.outcome = torch.stack(
            [self.embed(cell) * (1 if accepted else -1) for cell, accepted in outcomes]
        ).mean(0)
        self.refresh()

    def observe_reply(self, items, replies):
        if not self.conditioned:
            self.refresh()
            return
        self.reply(
            [(v.cell, replies[v.uid][1] == 0) for v in items if v.uid in replies]
        )


def split_draft(items, scheduled):
    """Only the leading token is offered to CCP. Its consumers remain editable."""
    if not items:
        return (), ()
    cell = items[0].cell
    if cell.rule not in scheduled or any(
        isinstance(r, Local) or r[2] < 0 for r in cell.refs
    ):
        return (), items
    return items[:1], items[1:]


def revise_references(items, resolve):
    revised = []
    for item in items:
        refs = tuple(resolve(r) for r in item.cell.refs)
        revised.append(
            item
            if refs == item.cell.refs
            else replace(item, cell=replace(item.cell, refs=refs))
        )
    return tuple(revised)


class ResponsePolicy(Ownership):
    def __init__(self, *args):
        super().__init__(*args)
        self.draft = ()

    def record_suffix_response(self, rid, refs, accepted):
        cell = Cell(rid, tuple(refs))
        signal = self.m.embed(cell) * (1 if accepted else -1)
        self.m.open_evidence = (self.m.open_evidence + signal).tanh()

    def record_boundary(self, inst, rid, i, src, pc, reason, stats):
        # Only the selected instruction and its own wire are inspected. Query guards
        # remain with the native rule. There is no list of environmental writers.
        slot = self.m.enc.nodes[self.m.enc.cat.inputs["generated", rid][i]]
        if src >= 0:
            producer = inst.unit[src][0]
            site = self.m.wire_contract(inst.unit, len(inst.owners), i)["source"]
            reason = reason + "/" + site["presence"]
            slot = slot + self.m.local_code(Cell(producer, ()), pc)
        self.m.open_evidence = (self.m.open_evidence + slot).tanh()
        stats["open_boundary/" + reason] += 1

    def resume_programs(self, frame, pub, txn, stats):
        def publication(ref):
            if not isinstance(ref, Local) and ref[2] < 0 and ref[0] != 0:
                stats["draft_named_publication_reads"] += 1
                hit = self.m.pub.live.get(ref[:2])
                if hit is not None:
                    stats["draft_named_publication_resolutions"] += 1
                    return (*ref[:2], hit[0]["version"])
            return ref

        self.draft = revise_references(self.draft, publication)
        self.m.open_evidence = ZERO
        super().resume_programs(frame, pub, txn, stats)
        self.m.refresh()

    def send(self, items, txn, stats):
        if not getattr(self, "fresh_requests", False):
            return super().send(items, txn, stats)
        # Keep internal verified continuation sharing, but charge every external
        # neural request to CCP and condition on its real reply.
        owned = self.owned
        self.owned = {}
        try:
            return super().send(items, txn, stats)
        finally:
            self.owned = owned

    def issue(self, items, txn, stats):
        replies = super().issue(items, txn, stats)
        if replies and self.draft:

            def receipt(ref):
                if isinstance(ref, Local) and ref.owner in replies:
                    row = replies[ref.owner]
                    # Negative versions are private draft states and can never be sent.
                    # Owner zero denotes a failed producer; only a neural edit can repair it.
                    return (int(row[0]) if row[1] == 0 else 0, ref.port, -1)
                return ref

            self.draft = revise_references(self.draft, receipt)
        return replies

    def dispatch_prefix(self, items, stats):
        start = perf_counter()
        stats["draft_after_edit"] += len(items)
        stats["edits_dropped_prior_tokens"] += sum(v not in items for v in self.draft)
        issued, self.draft = split_draft(items, self.scheduled)
        stats["draft_pending"] = len(self.draft)
        stats["carried_unissued"] += len(self.draft)
        stats["split_seconds"] += perf_counter() - start
        return issued

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        self.scheduled = dict(frame["rules"])
        return super().run_snapshot(frame, pub, rd, model, txn, stats, deadline)
