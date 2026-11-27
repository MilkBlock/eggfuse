"""Complete-Token CE with a named first reference and a static field projection."""

import torch

from interface_role_model import RoleRead, layouts
from operand_read_model import words


def typed_distribution(logp, tables, expected):
    allowed = tables == expected
    if not allowed.any():
        return None
    return logp.masked_fill(~allowed, -torch.inf).log_softmax(0)


def constructible_roots(logp, declarations, public_tables):
    """Condition on a nonempty typed address domain for every required slot."""
    present = set(public_tables.tolist())
    support = [all(table in present for table in roles) for roles in declarations]
    if not any(support):
        return logp.new_full(logp.shape, -torch.inf), False
    allowed = logp.new_tensor(support, dtype=torch.bool)
    return logp.masked_fill(~allowed, -torch.inf).log_softmax(0), True


class SelectedCell(RoleRead):
    condition_on_types = False

    def __init__(self, a, mode, typed):
        super().__init__(a, "C")
        self.mode = mode
        self.typed = typed

    def read_interface(self, query, ports):
        if self.mode == "legacy":
            return super().read_interface(query, ports)
        # Postpone operand reads until a particular published reference is chosen.
        return None

    def state(self, w, s):
        m = super().state(w, s)
        m["tables"] = torch.tensor([p[3] for p in m["ports"]], dtype=torch.long)
        if self.mode == "legacy":
            return m
        groups = {}
        for j, t in enumerate(m["menu"]):
            groups.setdefault(w.layouts[t][0][0], []).append(j)
        m["families"] = groups
        m["root_lp"] = torch.stack([m["lp"][js].logsumexp(0) for js in groups.values()])
        if self.condition_on_types:
            if not self.typed:
                raise ValueError("root and parent addressing must use the same type declarations")
            m["root_lp"], m["has_complete_domain"] = constructible_roots(
                m["root_lp"], (w.roles[rid] for rid in groups), m["tables"]
            )
        return m

    def address(self, w, m, tid, prefix):
        if not m["refs"]:
            return None
        lp = super().address(w, m, tid, prefix)
        if self.typed:
            rid = w.layouts[tid][0][0]
            return typed_distribution(lp, m["tables"], w.roles[rid][len(prefix)])
        return lp

    def variant_prob(self, w, m, rid, first):
        js = m["families"][rid]
        if len(js) == 1 or first is None:
            return m["lp"][js].log_softmax(0)
        ts = [m["menu"][j] for j in js]
        p = m["ports"][first]
        codes = self.cache[1][ts]
        query = self.actor.query(m["ctx"] + codes)
        fields, roles = words([p[4]])
        self.port_types = self.type_codes[[p[3]]]
        # Every member of this static family has the same entry rule and parent types.
        # On a foreign table no static accessor exists; use the learned field read.
        direct = self.mode == "direct" and p[3] == w.roles[rid][0]
        if direct:
            # Values are in native declaration order. A held physical permutation is
            # applied below, with an inverse layout for ordinary constant-column gathers.
            split, idx = self.physical
            orders = layouts(len(roles))[split == "held"]
            order = torch.tensor(orders[idx % len(orders)])
            stored = fields[:, order]
            columns = self.columns[ts]
            supported = (columns >= 0).all(-1) & (columns < len(roles)).all(-1)
            # Unresolved declarations take the learned path below. Do not project an
            # arbitrary field into their unused positions in the rectangular batch.
            resolved = supported.nonzero().flatten()
            chosen = order.argsort()[columns[resolved]]
            raw = stored.new_zeros((len(ts), 2, 64))
            raw[resolved] = stored[0, chosen]
            halves = raw.reshape(len(ts), 2, 2, 32)
            values = (
                halves
                + 0.25
                * self.actor.input_role(halves + 0.25 * self.port_types[0]).tanh()
            )
            relation = (values[:, 0] * values[:, 1]).mean(1)
            read = relation + self.actor.input_role(relation).tanh()
            if self.audit:
                self.projected_values = values
                self.projected_relation = relation
            fallback = [i for i, ok in enumerate(supported.tolist()) if not ok]
            if fallback:
                read = read.index_copy(
                    0,
                    torch.tensor(fallback),
                    self.learned_read(
                        query[fallback], fields, roles, [ts[i] for i in fallback]
                    ),
                )
        else:
            read = self.learned_read(query, fields, roles, ts)
        owner = m["group"][first]
        value = m["vals"][owner] + self.actor.latent(m["ext"][first]) + read
        return self.template_readout(m["ctx"], value, codes).log_softmax(0)

    def learned_read(self, q, fields, roles, ts):
        return self.payload(
            q[None], fields, roles, torch.ones(fields.shape[:2], dtype=torch.bool), ts
        )[0]

    def token_loss(self, w, m, target):
        if self.mode == "legacy":
            return super().token_loss(w, m, target)
        tid, refs = target
        rid = w.layouts[tid][0][0]
        ix = [m["pos"][r] for r in refs]
        root = list(m["families"]).index(rid)
        j = m["families"][rid].index(m["menu"].index(tid))
        lp = m["root_lp"][root] + self.variant_prob(w, m, rid, ix[0] if ix else None)[j]
        for k, addr in enumerate(ix):
            lp = lp + self.address(w, m, tid if k else rid, ix[:k])[addr]
        return -lp

    def sample(self, lp, rng):
        if not self.typed:
            return super().sample(lp, rng)
        # Sampling the support avoids choosing a masked address at either CDF endpoint.
        support = lp.isfinite().nonzero().flatten()
        cdf = lp[support].detach().double().exp().cumsum(0)
        i = torch.searchsorted(cdf, cdf[-1] * rng.random(), right=True)
        return int(support[i.clamp_max(len(support) - 1)])

    def generate(self, w, state, rng, slots):
        if self.mode == "legacy":
            return super().generate(w, state, rng, slots)
        if not state["menu"]:
            return []
        m = self.state(w, state)

        if not m.get("has_complete_domain", True):
            return []

        def draw(lp):
            return self.sample(lp, rng)

        out = []
        memo = m["memo"]

        def address(t, ix):
            key = t, tuple(ix)
            if key not in memo:
                memo[key] = self.address(w, m, t, ix)
            return memo[key]

        for _ in range(slots):
            rid = list(m["families"])[draw(m["root_lp"])]
            ix = []
            if w.roles[rid]:
                lp = address(rid, ix)
                if lp is None:
                    continue
                ix.append(draw(lp))
            key = ("variants", rid, tuple(ix))
            if key not in memo:
                memo[key] = self.variant_prob(w, m, rid, ix[0] if ix else None)
            j = m["families"][rid][draw(memo[key])]
            tid = m["menu"][j]
            for _role in w.roles[rid][1:]:
                lp = address(tid, ix)
                if lp is None:
                    break
                ix.append(draw(lp))
            else:
                out.append((tid, tuple(m["refs"][i] for i in ix)))
        return out
