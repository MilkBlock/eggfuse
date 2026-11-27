"""One full-token likelihood with Cell, external-port and field attention ablations."""

import math
import os

import numpy as np
import torch
from torch import nn


from actor import rotate
from binding_model import bit_lanes
from head_joint_index import PostingIndex
from partner_index import EXPLORE
from ripsat_policy import CellScorer, GraphBank
from rule_read import load_actor


def public_values(rows):
    """The original 32-lane row feature map, independently applied to every row."""
    out = np.zeros((len(rows), 32), np.float64)
    for j in range(max(map(len, rows), default=0)):
        ids = [i for i, row in enumerate(rows) if j < len(row)]
        words = np.asarray([rows[i][j] for i in ids], dtype=np.uint64)
        shifts = (np.arange(32, dtype=np.uint64) + 7 * j) % 64
        out[ids] += (2 * ((words[:, None] >> shifts) & 1).astype(np.float64) - 1) / (
            1 + j
        )
    return torch.from_numpy(out.astype(np.float32))


class CellKV(nn.Module):
    def __init__(self, a, arm, train_graph):
        super().__init__()
        self.arm = arm
        self.read_ports_at_template = os.environ.get("KV_READOUT", "full") == "full"
        self.actor = load_actor(a.actor, True).cpu()
        self.graph = CellScorer(32)
        self.graph.load_state_dict(
            torch.load(
                "run-recall/parameterized-deep-ripsat/event-gnn.pt",
                map_location="cpu",
                weights_only=True,
            )["model"]
        )
        self.train_graph = train_graph
        self.static_cache = {}
        if not train_graph:
            for layer in self.graph_modules():
                layer.requires_grad_(False)
        if arm in ("A", "U"):
            from partner_index_worlds import frozen

            legacy = frozen(a, a.seeds[0]).cpu()
            self.mapping = legacy.mapping.requires_grad_(False)
        self.cache = None

    def load_state_dict(self, *args, **kwargs):
        self.cache = None
        self.static_cache.clear()
        return super().load_state_dict(*args, **kwargs)

    def graph_modules(self):
        return [self.actor.static, self.actor.msg, self.actor.update, self.graph]

    def structure(self, w):
        nodes = self.actor.template_graph(w.cat)
        # Bucket the two static granularities before graph encoding. A 256-step
        # template must not pad every Primitive in the catalogue to 256 steps.
        codes = torch.cat(
            [
                GraphBank(layouts, w.cat, nodes).encode(self.graph)
                for layouts in (w.layouts[: w.primitives], w.layouts[w.primitives :])
                if layouts
            ]
        )
        types = nodes[[w.cat.roots["initial", i] for i in range(len(w.tabs))]]
        return nodes, codes, types

    def prepare(self, w):
        if self.training and self.train_graph:
            self.static_cache.clear()
            self.cache = self.structure(w)
        else:
            if w not in self.static_cache:
                with torch.no_grad():
                    self.static_cache[w] = self.structure(w)
            self.cache = self.static_cache[w]

    def state(self, w, s):
        nodes, codes, types = self.cache
        ports = s["ports"]
        refs = [p[0] for p in ports]
        positions = {ref: i for i, ref in enumerate(refs)}
        owners = {}
        member_lists = []
        group = []
        for index, (_, uid, *_) in enumerate(ports):
            if uid not in owners:
                owners[uid] = len(member_lists)
                member_lists.append([])
            ordinal = owners[uid]
            member_lists[ordinal].append(index)
            group.append(ordinal)
        group = torch.tensor(group)
        tables = torch.tensor([p[3] for p in ports], dtype=torch.long)
        dyn = self.actor.dynamic(public_values([p[4] for p in ports]))
        age = dyn.new_tensor(
            [
                [math.log1p(max(0, s["epoch"] - ref[2])) / 8, float(p[5])]
                for ref, p in zip(refs, ports)
            ]
        )
        value = (types[tables] + dyn + self.actor.age(age.reshape(-1, 2))).tanh()
        source = types[tables].clone()
        generated = [i for i, p in enumerate(ports) if p[2] >= 0]
        if generated:
            source[generated] = codes[[ports[i][2] for i in generated]]
        siblings = [torch.tensor(ix) for ix in member_lists]
        owner_values, value = self.instance_embedding(
            w, ports, positions, siblings, group, source, value
        )
        keys = self.actor.input_content(owner_values)
        vals = self.actor.latent(owner_values)
        menu = s["menu"]
        runtime = keys.new_zeros(32)
        runtime[:5] = (
            torch.log1p(keys.new_tensor([s["run"], s["epoch"], *s["response"]])) / 8
        )
        q = self.actor.query(self.actor.lanes.weight[0] + runtime)
        ctx = self.actor.next_read(
            ((keys @ q) / math.sqrt(32)).softmax(0) @ vals, self.actor.lanes.weight[0]
        )
        # Each template can read all named Cell owners before template selection.
        query = self.actor.query(ctx + codes[menu])
        read = ((query @ keys.T) / math.sqrt(32)).softmax(1) @ vals
        ext_keys = self.actor.input_content(value)
        fields = None
        if self.arm == "D" and ports:
            width = max(len(p[4]) for p in ports)
            pad = [p[4] + (0,) * (width - len(p[4])) for p in ports]
            bits = torch.from_numpy(bit_lanes(pad))
            # Preserve 64-bit input using both 32-lane halves and the shared projections.
            fields = (
                self.actor.dynamic(bits[:, :, :32])
                + self.actor.input_content(bits[:, :, 32:])
            ).tanh()
        if self.read_ports_at_template and self.arm in ("C", "D") and siblings:
            # Each candidate Cell program reads its possible operands at the
            # requested resolution. Ownership is retained at both reductions.
            pv = self.actor.latent(value)[None].expand(len(menu), -1, -1)
            if fields is not None and fields.size(1):
                roles = torch.arange(fields.size(1))[None, :].expand(fields.size(0), -1)
                field_keys = rotate(fields.flatten(0, 1), roles.flatten()).view_as(
                    fields
                )
                scores = torch.einsum("qd,pfd->qpf", query, field_keys) / math.sqrt(32)
                real = roles < torch.tensor([len(p[4]) for p in ports])[:, None]
                safe = scores.masked_fill(~real[None], -torch.inf)
                weights = (
                    torch.where(real.any(1)[None, :, None], safe, 0.0).softmax(2)
                    * real[None]
                )
                pv = pv + torch.einsum("qpf,pfd->qpd", weights, fields)
            port_logits = query @ ext_keys.T / math.sqrt(32)
            messages = torch.stack(
                [
                    torch.einsum("qp,qpd->qd", port_logits[:, ix].softmax(1), pv[:, ix])
                    for ix in siblings
                ],
                1,
            )
            context_values = vals[None] + messages
            owner_logits = query @ keys.T / math.sqrt(32) + (
                messages * query[:, None]
            ).sum(-1) / math.sqrt(32)
            owner_weights = owner_logits.softmax(1)
            interface = self.read_interface(query, ports)
            if interface is not None:
                # Reuse neural owner and public-port selection. Only the payload
                # being read changes, after the address weights are known.
                context_values = context_values + torch.stack(
                    [
                        torch.einsum(
                            "qp,qpd->qd",
                            port_logits[:, ix].softmax(1),
                            interface[:, ix],
                        )
                        for ix in siblings
                    ],
                    1,
                )
            read = (owner_weights[:, :, None] * context_values).sum(1)
        tlog = self.template_readout(ctx, read, codes[menu])
        return dict(
            ports=ports,
            refs=refs,
            pos=positions,
            group=group,
            siblings=siblings,
            owners=owner_values,
            keys=keys,
            vals=vals,
            ctx=ctx,
            menu=menu,
            lp=tlog.log_softmax(0),
            ext=value,
            ek=ext_keys,
            fields=fields,
            memo={},
        )

    def read_interface(self, query, ports):
        return None

    def template_readout(self, ctx, read, codes):
        return (self.actor.query(ctx + read) * self.actor.input_role(codes)).sum(
            -1
        ) / math.sqrt(32)

    def instance_embedding(self, w, ports, positions, siblings, group, source, value):
        """Encode published Cell instances before the shared attention projections."""
        parent_vectors = []
        for i, p in enumerate(ports):
            hits = [positions[r] for r in p[6] if r in positions]
            parent_vectors.append(
                value[hits].mean(0) if hits else torch.zeros_like(value[i])
            )
        owner_values = (
            torch.stack(
                [
                    (
                        source[ix[0]]
                        + value[ix].mean(0)
                        + torch.stack([parent_vectors[i] for i in ix.tolist()]).mean(0)
                    ).tanh()
                    for ix in siblings
                ]
            )
            if siblings
            else value
        )
        return owner_values, value

    def domains(self, m, tabs):
        if self.arm == "U":
            return [list(range(len(m["ports"]))) for _ in tabs]
        return [[i for i, p in enumerate(m["ports"]) if p[3] == t] for t in tabs]

    def sparse_prob(self, w, m, rid, j, prefix, q):
        # Baseline uses static type domains and A's frozen joint neural kernel.
        # This experiment has unary rules plus a two-parent final consumer.
        tabs = w.roles[rid]
        banks = self.domains(m, tabs)
        ix = banks[j]
        if not ix or any(not bank for bank in banks):
            return None
        p0 = m["ek"][banks[0]] @ q / math.sqrt(32)
        if len(banks) > 1:
            tag = ("posting", rid)
            if tag not in m["memo"]:
                rows = w.prog["recipe"]["rules"][rid]["interface"]["rows"]
                wires = [
                    (a, b)
                    for a, x in enumerate(rows[0]["columns"])
                    for b, y in enumerate(rows[1]["columns"])
                    if x.get("slot") is not None and x.get("slot") == y.get("slot")
                ]
                feats = []
                for t, bank in enumerate(banks):
                    data = np.array(
                        [
                            [
                                (
                                    m["ports"][i][4][ab[t]]
                                    if ab[t] < len(m["ports"][i][4])
                                    else 0
                                )
                                for ab in wires
                            ]
                            for i in bank
                        ],
                        dtype=np.uint64,
                    )
                    feats.append(
                        self.mapping(
                            torch.from_numpy(bit_lanes(data))[None],
                            "mixed-sparse",
                            fixed_order=True,
                        )
                    )
                posting = PostingIndex.build(feats[1], torch.ones(1, len(banks[1])))
                start, count, mass = posting.lookup(feats[0])
                m["memo"][tag] = posting, start, count, mass
            posting, start, count, mass = m["memo"][tag]
            if j == 0:
                p0 = p0 + (mass.sum(-1)[0] + 1e-12).log()
            else:
                # Exact marginal for CE on this small control. Free draws use
                # Edge.draw's two-stage posting sampler, below.
                src = banks[0].index(prefix[0])
                mass = mass[0, src]
                tot = mass.sum()
                prob = torch.full((len(ix),), 1 / len(ix))
                if float(tot) > 0:
                    freq = torch.zeros_like(prob)
                    for st, n, wt in zip(start[0, src], count[0, src], mass / tot):
                        if not int(n):
                            continue
                        lo = (
                            int(torch.searchsorted(posting.ends[0], st, right=True)) - 1
                        )
                        hi = int(
                            torch.searchsorted(posting.ends[0], st + n, right=False)
                        )
                        ends = posting.ends[0, lo : hi + 1]
                        freq.index_add_(
                            0,
                            posting.owners[0, lo:hi].long(),
                            (ends.diff().float() / n) * wt,
                        )
                    prob = EXPLORE / len(ix) + (1 - EXPLORE) * freq
                full = q.new_full((len(m["refs"]),), -torch.inf)
                full[ix] = prob.clamp_min(1e-30).log()
                return full
        p = p0.softmax(0)
        full = q.new_full((len(m["refs"]),), -torch.inf)
        full[ix] = (p * (1 - EXPLORE) + EXPLORE / len(ix)).log()
        return full

    def address(self, w, m, tid, prefix):
        nodes, codes, _ = self.cache
        rid = w.layouts[tid][0][0]
        j = len(prefix)
        role = nodes[w.cat.inputs["generated", rid][j]]
        h = (m["ctx"] + codes[tid]).tanh()
        for idx in prefix:
            h = self.actor.next_read(m["ext"][idx], h)
        q = self.actor.query(h + role)
        if self.arm in ("A", "U"):
            return self.sparse_prob(w, m, rid, j, prefix, q)
        owner = m["keys"] @ q / math.sqrt(32)
        port = q.new_zeros(len(m["refs"]))
        if self.arm in ("C", "D"):
            port = m["ek"] @ q / math.sqrt(32)
            if self.arm == "D":
                fq = q
                if prefix:
                    src = m["fields"][prefix[-1], : len(m["ports"][prefix[-1]][4])]
                    fq = fq + ((src @ q) / math.sqrt(32)).softmax(0) @ src
                # No comparisons or pruning by field identity. Mask only padding.
                mask = (
                    torch.arange(m["fields"].shape[1])[None, :]
                    < torch.tensor([len(p[4]) for p in m["ports"]])[:, None]
                )
                fs = (m["fields"] @ fq) / math.sqrt(32)
                present = mask.any(1)
                if mask.shape[1]:
                    fs = fs.masked_fill(~mask, -torch.inf)
                    safe = torch.where(present[:, None], fs, torch.zeros_like(fs))
                    port = port + torch.where(
                        present, safe.logsumexp(1) - mask.sum(1).clamp_min(1).log(), 0.0
                    )
            # Attention to public ports contributes to the owner choice.
            owner = owner + torch.stack(
                [port[ix].logsumexp(0) - math.log(len(ix)) for ix in m["siblings"]]
            )
        owner = owner.log_softmax(0)
        norm = torch.stack([port[ix].logsumexp(0) for ix in m["siblings"]])
        return owner[m["group"]] + port - norm[m["group"]]

    def token_loss(self, w, m, target):
        t, refs = target
        terms = [m["lp"][m["menu"].index(t)]]
        prefix = []
        for ref in refs:
            i = m["pos"][ref]
            terms.append(self.address(w, m, t, prefix)[i])
            prefix.append(i)
        return -torch.stack(terms).sum()

    @staticmethod
    def sample(lp, rng):
        return int(
            torch.searchsorted(
                lp.detach().exp().cumsum(0), torch.tensor(rng.random())
            ).clamp_max(len(lp) - 1)
        )

    def generate(self, w, state, rng, slots):
        if not state["menu"]:
            return []
        m = self.state(w, state)

        out = []
        for _ in range(slots):
            tid = m["menu"][self.sample(m["lp"], rng)]
            rid = w.layouts[tid][0][0]
            choices = []
            for j in range(len(w.roles[rid])):
                if not m["refs"]:
                    break
                key = tid, tuple(choices)
                if self.arm in ("A", "U") and j == 1:
                    from head_joint_index import Edge

                    posting, start, count, mass = m["memo"]["posting", rid]
                    banks = self.domains(m, w.roles[rid])
                    root = banks[0].index(choices[0])
                    noise = torch.from_numpy(rng.random((1, 1, 5), dtype=np.float32))
                    result = Edge(posting, start, count, mass).draw(
                        torch.tensor([[root]]), noise
                    )
                    choices.append(banks[1][int(result)])
                    continue
                if key not in m["memo"]:
                    m["memo"][key] = self.address(w, m, tid, choices)
                if m["memo"][key] is None:
                    break
                choices.append(self.sample(m["memo"][key], rng))
            else:
                out.append((tid, tuple(m["refs"][i] for i in choices)))
        return out
