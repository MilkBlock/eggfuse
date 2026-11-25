"""Open Recipe continuations for B. Every dynamic operand is a named receipt."""
from collections import Counter, defaultdict
from dataclasses import dataclass
import numpy as np
import torch

from cell_transaction import STATUS
from entry_model import scores
from event_templates import shape
from higher_replacement import send
from projected_entries import ProjectedEntries

ACTIONS = ("Primitive", "Activate", "Extend", "Compose", "Defer")


@dataclass(frozen=True)
class Continuation:
    rule: int
    source_role: int
    # Table types of the independent evidence still needed, in Recipe order.
    remaining: tuple


def compile_boundary(rules):
    # Reuse the original producer, presence and merge guard descriptors.
    exports = {r: tuple((int(op), site) for op, site in rule["outputs"].items())
               for r, rule in enumerate(rules)}
    plans = {}
    for r, rule in enumerate(rules):
        inputs = rule["inputs"]
        for j in range(len(inputs)):
            plans[r, j] = Continuation(r, j, tuple((i, v["table"]) for i, v in enumerate(inputs) if i != j))
    return exports, plans


class OpenEntries(ProjectedEntries):
    def __init__(self, program, store, weights, graph, contracts, rules):
        super().__init__(program, store, weights, graph, contracts, rules)
        self.exports, self.plans = compile_boundary(rules)
        self.open_ports = {}
        self.recent = defaultdict(dict)
        self.publish_next = []
        self.deferred = {}
        self.action_counts = Counter()
        self.action_runs = set()
        self.lineage = []
        self.decisions = 0
        self.base_codes = {}
        self.live_open = {}
        self.exploration = None
        self.suffix_tokens = {}

    def event_route(self, key, pos):
        routes = self.routes.get(key, ())
        if len(routes) < 2:
            return routes[0] if routes else None
        uid, role, _, _ = key
        r = self.family.units[uid][0][0]
        codes = []
        for _, contract in routes:
            x = self.code(self.mem, r, role).copy()
            for j, (kind, slot) in enumerate(contract["reads"]):
                x[(2*j) % len(x)] += 1 if kind == "input" else -1
                x[(2*j+1) % len(x)] += np.log1p(slot)/8
            codes.append(x)
        event = self.mem.bank(self.mem.roles[r][role]).vec[pos:pos+1]
        logits = scores(self.model, torch.from_numpy(event), torch.from_numpy(np.stack(codes)))
        self.count["open_contract_choices"] += 1
        return routes[int(logits.argmax())]

    def publish(self, rd, token, rule, depth, parent_ids):
        actual = []
        for op, site in self.exports[rule]:
            table = site["table"]
            addr = token, op
            row = rd.store.visible.get(addr)
            if row is None:
                continue
            if row["table"] != table:
                raise ValueError("receipt disagrees with Recipe output")
            ref = (*addr, int(row["version"]))
            self.open_ports[ref] = depth
            self.recent[table][ref] = None
            actual.append(ref)
        if actual:
            self.lineage.append((token, depth, parent_ids, actual))
            self.count["max_abstraction_depth"] = max(self.count["max_abstraction_depth"], depth)

    def start(self, rd, pub, txn, rules, stats):
        self.txn = txn
        self.suffix_positions = defaultdict(set)
        self.count = stats
        # A changed/retired receipt cannot inherit the old computation's evidence.
        for block in (pub[2], pub[0]):
            for row in block:
                addr = tuple(map(int, row[:2]))
                old = self.live_open.pop(addr, None)
                if old:
                    table, ref = old
                    self.open_ports.pop(ref, None)
                    self.recent[table].pop(ref, None)
        pending = self.publish_next
        self.publish_next = []
        for uid, _, tokens, _, step in self.waiting:
            unit = self.cat.units[uid]
            if step == len(unit):
                pending.append((tokens[-1], unit[-1][0], 1, tuple(tokens[:-1])))
        super().start(rd, pub, txn, rules, stats)
        accepted = set(map(int, pub[3][:, 0]))
        for token, rule, depth, parents in pending:
            if token not in accepted:
                raise ValueError("unpublished continuation")
            size = len(self.lineage)
            self.publish(rd, token, rule, depth, parents)
            if len(self.lineage) > size:
                for ref in self.lineage[-1][-1]:
                    self.live_open[ref[:2]] = (rd.store.visible[ref[:2]]["table"], ref)
        self.retry_ready = True

    def code(self, mem, r, j):
        key = (r, j)
        if key not in self.base_codes:
            if key in self.family.codes:
                self.base_codes[key] = self.family.codes[key][0]
            else:
                s = shape(mem.rd, r, j)
                self.base_codes[key] = np.asarray([*s, *s, 0., 0.], np.float32)
        return self.base_codes[key]

    def act(self, r, j, pos, mem, *, retry=False):
        plan = self.plans[r, j]
        if len(plan.remaining) > 1:
            return
        srcbank = mem.bank(mem.roles[r][j])
        src = tuple(map(int, srcbank.rows[pos]))
        depth = self.open_ports.get(src, 0)
        target = plan.remaining[0] if plan.remaining else None
        table = target[1] if target else None
        recent = self.recent.get(table, {})
        if not depth and not recent:
            return
        # Pick an operation before resolving its missing operand. No pair by value.
        codes, actions = [], []
        base = self.code(mem, r, j)
        def option(name, code, arg=None):
            x = code.copy()
            if name in ("Extend", "Compose", "Defer"):
                x[-5 + ACTIONS.index(name)] += 1
                x[0] += np.log1p(depth) / 8
                x[1] += float(bool(recent)) / 8
            codes.append(x)
            actions.append((name, arg))

        option("Primitive", base)
        for i, uid in enumerate(self.family.menu.get(r, ())):
            option("Activate", self.family.codes[r, j][i + 1], uid)
        if depth or (target and recent):
            option("Extend", base)
        if depth and target and recent:
            option("Compose", base)
        self.structure_options(r, j, base, depth, target, recent, option)
        if not retry:
            option("Defer", base)
        x = torch.from_numpy(srcbank.vec[pos:pos + 1])
        logits = scores(self.model, x, torch.from_numpy(np.stack(codes)))
        k = int(logits.argmax())
        if self.exploration is not None and self.exploration.random() < .20:
            k = int(self.exploration.integers(len(actions)))
        action, uid = actions[k]
        self.action_counts[action] += 1
        self.action_runs.add(self.txn.run)
        self.decisions += 1
        self.count["open_action_scores"] += len(codes)
        if action == "Defer":
            self.deferred[r, j, src] = self.txn.run
            # Defer only the optional composition. Keep ordinary B coverage live.
            return
        if action == "Activate":
            if not retry:
                self.choice[pos] = uid
            else:
                # A retried Activate still has to bind and natively win its root.
                self.retry_activation(r, j, src, uid, mem)
            return
        if not retry:
            self.choice.pop(pos, None)
        if action == "Primitive":
            return
        mode = action.removeprefix("Wired")
        refs = [src]
        if target:
            if mode == "Compose" or not depth:
                other = self.open_partner(r, j, pos, src, target, recent, mem, mode)
                if other is None:
                    return
            else:
                # The existing B pointer supplies the independent operand.
                # Its posting visits and neural scores are charged by bind().
                wires = tuple((-1, role) for role in range(len(mem.roles[r])))
                other = self.bind(r, wires, target[0], {j: src})
                if other is None:
                    return
                other = tuple(map(int, other))
            self.count["open_operand_reads"] += 1
            if mode == "Compose" and src[0] == other[0]:
                self.count["open_same_parent_Compose"] += 1
                return
            if mode == "Extend" and depth and other in self.open_ports:
                self.count["open_partner_already_composite"] += 1
                return
            refs.insert(target[0], other)
        if uid is None:
            self.issue_suffix(r, tuple(refs), mode, mem)
        else:
            self.issue_structure(r, tuple(refs), mode, mem, uid)

    def structure_options(self, r, j, base, depth, target, recent, option):
        pass

    def open_partner(self, r, j, pos, src, target, recent, mem, mode):
        it = reversed(recent)
        other = next(it)
        if mode == "Compose" and src[0] == other[0] and len(recent) > 1:
            other = next(it)
            self.count["open_operand_reads"] += 1
        return other

    def retry_activation(self, r, j, src, uid, mem):
        kind, owner_rule = mem.rd.store.types[src[0]]
        if kind != "generated":
            return
        route = self.route((uid, j, owner_rule, src[1]))
        if route is None:
            return
        from multi_entry import resolve
        refs = resolve(route[1]["reads"], src[0], self.owners.get(src[0], ()), mem.rd.store.visible)
        if refs is not None:
            self.issue_suffix(r, refs, "Activate", mem, uid)

    def issue_suffix(self, r, refs, action, mem, uid=None):
        parent_levels = {ref[0]: self.open_ports[ref] for ref in refs if ref in self.open_ports}
        if uid is None and len(parent_levels) != {"Extend": 1, "Compose": 2}[action]:
            return
        if refs in self.done[r]:
            self.count["open_already_signed_" + action] += 1
            return
        for t, pc, v in refs:
            row = mem.rd.store.visible.get((t, pc))
            if row is None or row["version"] != v:
                self.count["open_stale_" + action] += 1
                return
        if mem.rd.iface.rules[r]["metadata"]["seminaive"] and max(v for _, _, v in refs) < self.rules[r]:
            self.count["open_old_only_" + action] += 1
            return
        response = send(self.txn, r, np.asarray([refs], np.int64))[0]
        self.count["open_issued_" + action] += 1
        # Legacy counter is the physical request width, including the source.
        self.count["open_independent_bindings"] += len(refs)
        self.count["open_new_bindings"] += len(refs) - 1 if uid is None else 0
        self.count["open_reply_" + action + "_" + STATUS[int(response[1])]] += 1
        if response[1] != 0:
            return
        token = int(response[0])
        self.count["open_accepted_" + action] += 1
        if uid is None:
            parents = tuple(parent_levels)
            level = 1 + max(parent_levels.values())
            self.publish_next.append((token, r, level, parents))
            self.suffix_tokens[token] = (action, level)
            self.suffix_positions[r].add(tuple(mem.bank(table).positions[ref[:2]]
                                               for table, ref in zip(mem.roles[r], refs, strict=True)))
        else:
            self.begin(uid, refs, token, self.txn)
        self.done[r].add(refs)
        self.covered_rules[r] = self.done[r]
        for key in tuple(self.covered_indices):
            if key[0] == r:
                del self.covered_indices[key]
        return token

    def choose(self, r, j, ix, mem, woke):
        super().choose(r, j, ix, mem, woke)
        if self.retry_ready:
            self.retry_ready = False
            for key, previous in tuple(self.deferred.items()):
                rule, role, ref = key
                if previous >= self.txn.run or rule not in self.rules:
                    continue
                del self.deferred[key]
                bank = mem.bank(mem.roles[rule][role])
                k = bank.positions.get(ref[:2])
                if k is not None and bank.rows[k, 2] == ref[2]:
                    self.count["open_resumes"] += 1
                    self.act(rule, role, k, mem, retry=True)
        if j >= 0 and self.open_ports and len(ix):
            # Two sparse events at most per existing B dispatch page; the entire
            # frozen residual stream still visits the rest of the page.
            event = int(ix[-1])
            table = mem.roles[r][j]
            recent = self.recent.get(table)
            if recent:
                addr = next(reversed(recent))[:2]
                pos = mem.bank(table).positions.get(addr)
                if pos is not None and pos != event:
                    self.count["open_page_position_checks"] += len(ix)
                    if np.any(ix == pos):
                        self.act(r, j, pos, mem)
            self.act(r, j, event, mem)
