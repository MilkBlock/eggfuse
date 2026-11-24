"""Choose typed computation requests before retrieving the next proof role."""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import torch
from torch import nn

from stream_guard import GuardStream, Study


@dataclass(frozen=True)
class ReadPlan:
    atom: int
    operands: tuple
    output_column: int
    prerequisites: tuple = ()

    @property
    def steps(self):
        return (*self.prerequisites, (self.atom, self.operands))


def plans(rd, rule, depth, chains=False):
    order = rd.order(rule)
    roles = rd.iface.roles[rule]
    sources = {}
    for i, role in enumerate(order[:depth]):
        for col, slot in enumerate(roles[role][1]):
            if slot is not None:
                sources.setdefault(slot, (i, col))
    target = roles[order[depth]][1]
    result = []
    query = rd.iface.rules[rule]["query"]
    producers = {}
    for pc, atom in enumerate(query):
        if "primitive" not in atom["call"]:
            continue
        out = atom["args"][-1].get("slot")
        if out is None:
            continue
        if out in target:
            steps = []
            cache = {}

            def compile_step(i):
                if i in cache:
                    return cache[i]
                operands = []
                for arg in query[i]["args"][:-1]:
                    slot = arg.get("slot")
                    if slot is None:
                        operands.append(None)
                    elif slot in sources:
                        operands.append(sources[slot])
                    elif chains and slot in producers and producers[slot] < i:
                        operands.append(("local", compile_step(producers[slot])))
                    else:
                        raise KeyError(slot)
                if not operands:
                    raise KeyError("zero-arity")
                cache[i] = len(steps)
                steps.append((i, tuple(operands)))
                return cache[i]

            try:
                compile_step(pc)
            except KeyError:
                pass
            else:
                result.append(
                    ReadPlan(pc, steps[-1][1], target.index(out), tuple(steps[:-1]))
                )
        producers.setdefault(out, pc)
    return result


class TransactionNet(nn.Module):
    width = 6

    def __init__(self):
        super().__init__()
        self.route = nn.Sequential(nn.Linear(5, 16), nn.Tanh(), nn.Linear(16, 1))
        self.planes = nn.Linear(24, self.width, bias=False)

    def code(self, h):
        return ((self.planes(h) >= 0).long() * (2 ** torch.arange(self.width))).sum(-1)


def route_features(size, occupancy, depth, plan):
    n = len(occupancy)
    operands = [a for _, args in plan.steps for a in args]
    return torch.stack(
        (
            torch.full((n,), float(size)).log1p(),
            occupancy.float().log1p(),
            torch.full((n,), depth / 4),
            torch.full((n,), len(operands) / 4),
            torch.full((n,), len(set(operands)) / 4),
        ),
        dim=1,
    )


class ResponsePolicy(Study):
    def __init__(self, root, mode="learned"):
        super().__init__(bits=8, symmetric=True, delta_buckets=True)
        self.chains = mode == "chain"
        self.net = TransactionNet().eval()
        self.net.load_state_dict(
            torch.load(
                Path(root)
                / ("txn-chain-study" if self.chains else "txn-study")
                / "model.pt",
                weights_only=True,
            )
        )
        if mode not in {"learned", "always", "random-address", "chain"}:
            raise ValueError(f"unknown transaction policy {mode}")
        if mode == "random-address":
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(57193)
                self.net.planes.reset_parameters()
        self.mode = mode

    def stream(self, *args):
        return ResponseStream(*args, study=self)


class ResponseStream(GuardStream):
    def __init__(self, *args, study):
        super().__init__(*args, study=study)
        self.joint_index = {}
        self.choices = {}

    def programs(self, depth):
        return plans(self.rd, self.rule, depth, self.study.chains)

    def issue_program(self, plan, inputs):
        if plan.prerequisites:
            self.stats["chain_prefixes"] += len(inputs[0])
            return self.transaction.compute_chain(
                self.rule, tuple(i for i, _ in plan.steps), inputs
            )
        return self.transaction.compute(self.rule, plan.atom, inputs[0])

    def select_query(self, success, occupancy, narrowed):
        return torch.ones(len(narrowed), dtype=torch.bool)

    def children(self, paths, depth, block):
        if depth not in self.choices:
            self.choices[depth] = [
                plan
                for plan in self.programs(depth)
                if len(plan.steps) <= self.transaction.capacity
            ]
        choices = self.choices[depth]
        if not choices or not depth:
            yield from super().children(paths, depth, block)
            return
        if depth not in self.joint_index:
            tick = perf_counter()
            if self.links[depth]:
                a, c, d = self.links[depth][0]
                src = torch.tensor([self.rd.index.rows[k][2][c] for k in self.roles[a]])
                dest = torch.tensor(
                    [self.rd.index.rows[k][2][d] for k in self.roles[depth]]
                )
            else:
                # A computable primitive may be the first link to this typed role.
                a = 0
                src = torch.zeros(len(self.roles[a]), dtype=torch.long)
                dest = torch.zeros(len(self.roles[depth]), dtype=torch.long)
            positions = torch.arange(len(dest))
            codes = [dest]
            idx = [positions]
            self.stats["index_items"] += len(src) + len(dest)
            width = 2**self.study.net.width
            self.stats["learned_index_keys"] += len(dest) * len(choices)
            for j, plan in enumerate(choices):
                field = self.tables[depth][3][:, plan.output_column]
                code = self.study.net.code(field)
                codes.append(256 + j * 256 * width + dest * width + code)
                idx.append(positions)
            codes = torch.cat(codes)
            idx = torch.cat(idx)
            span = 256 + len(choices) * 256 * width
            selective = self.semi and depth + 1 == len(self.roles)
            if selective:
                fresh = self.tables[depth][0][idx]
                codes = torch.cat((codes, codes[fresh] + span))
                idx = torch.cat((idx, idx[fresh]))
            order = idx[codes.argsort(stable=True)]
            offsets = torch.cat(
                (
                    torch.zeros(1, dtype=torch.long),
                    codes.bincount(minlength=span * (1 + selective)).cumsum(0),
                )
            )
            self.joint_index[depth] = (a, src, span, offsets, order, selective)
            self.stats["txn_index_seconds"] += perf_counter() - tick
            self.stats["index_items"] += len(codes)
        a, src, span, offsets, order, selective = self.joint_index[depth]
        direct = src[paths[:, a]]
        shift = torch.zeros_like(direct)
        if selective:
            fresh = torch.stack(
                [self.tables[i][0][paths[:, i]] for i in range(depth)]
            ).any(0)
            shift = (~fresh).long() * span
        direct_slot = direct + shift
        occupancy = offsets[direct_slot + 1] - offsets[direct_slot]
        scores = torch.stack(
            [
                self.study.net.route(
                    route_features(len(self.roles[depth]), occupancy, depth, p)
                ).flatten()
                for p in choices
            ],
            1,
        )
        score, choice = scores.max(1)
        self.stats["transaction_decisions"] += len(score)
        use = (score > 0) & (occupancy > 0)
        if self.study.mode == "always":
            use = occupancy > 0
        slot = direct_slot.clone()
        for j, plan in enumerate(choices):
            selected = torch.where(use & (choice == j))[0]
            if not len(selected):
                continue
            inputs = []
            for _, args in plan.steps:
                refs = []
                for link in args:
                    if link is None or link[0] == "local":
                        index = -1 if link is None else link[1]
                        refs.append(
                            torch.tensor([0, index, 0, 0]).expand(len(selected), 4)
                        )
                    else:
                        i, col = link
                        addr = self.port_refs(i)[paths[selected, i]]
                        refs.append(
                            torch.cat((addr, addr.new_full((len(addr), 1), col)), 1)
                        )
                inputs.append(torch.stack(refs, 1))
            reply = self.issue_program(plan, inputs)
            success = reply[:, 1] == 14
            selected = selected[success]
            self.stats["computed_valid"] += len(selected)
            self.stats["computed_fallback"] += int((~success).sum())
            if len(selected):
                raw = (
                    (reply[success, 3, None] >> torch.arange(63, -1, -1)) & 1
                ).float() * 2 - 1
                key = self.rd.index.encoder(raw)
                learned = self.study.net.code(key)
                width = 2**self.study.net.width
                query_slot = (
                    shift[selected]
                    + 256
                    + j * 256 * width
                    + direct[selected] * width
                    + learned
                )
                retain = self.select_query(
                    success,
                    occupancy[selected],
                    offsets[query_slot + 1] - offsets[query_slot],
                )
                slot[selected[retain]] = query_slot[retain]
                self.stats["response_queries"] += int(retain.sum())
                self.stats["response_direct_queries"] += int((~retain).sum())
        self.stats["direct_only_queries"] += int((~use).sum())
        self.stats["bucket_probes"] += len(slot)
        ends = (offsets[slot + 1] - offsets[slot]).cumsum(0)
        total = int(ends[-1])
        starts = torch.cat((ends.new_zeros(1), ends[:-1]))
        self.stats["bucket_items"] += total
        for begin in range(0, total, block):
            ix = torch.arange(begin, min(begin + block, total))
            parent = torch.searchsorted(ends, ix, right=True)
            yield parent, order[offsets[slot[parent]] + ix - starts[parent]]
