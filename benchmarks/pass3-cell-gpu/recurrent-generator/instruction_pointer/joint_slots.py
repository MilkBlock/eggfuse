"""Simultaneous neural reads from the typed boundary slots of a baked Cell."""
import math

import torch
from torch import nn


class JointSlots(nn.Module):
    def __init__(self, width, proposals):
        super().__init__()
        self.intent = nn.Parameter(torch.randn(proposals, width) / math.sqrt(width))
        self.query = nn.Linear(width, width)
        self.key = nn.Linear(width, width)
        self.fresh = nn.Parameter(torch.zeros(width))
        self.context = nn.GRUCell(width, width)
        self.field_weight = nn.Parameter(torch.ones(()))
        self.stop = nn.Linear(width, 1)

    def forward(self, root, roles, keys, fields, fresh, wiring, rounds):
        """Candidates are unordered within each role. Wiring lists (src, col, dst, col).

        Each proposal has its own distribution for each external role. All
        messages in one refinement read the preceding complete set of marginals.
        """
        if any(not len(k) for k in keys):
            raise ValueError('an empty required boundary domain cannot issue a tuple')
        states = [self.intent + root + role for role in roles]
        projected = [self.key(k + f[:, None] * self.fresh) for k, f in zip(keys, fresh, strict=True)]
        messages = [root.new_zeros((len(self.intent), len(k))) for k in keys]
        for step in range(rounds + 1):
            logits = [self.query(h) @ k.T / math.sqrt(h.shape[-1]) + m
                      for h, k, m in zip(states, projected, messages, strict=True)]
            if step == rounds:
                break
            weights = [score.softmax(-1) for score in logits]
            reads = [w @ k for w, k in zip(weights, keys, strict=True)]
            messages = [torch.zeros_like(score) for score in logits]
            for src, left, dst, right in wiring:
                expected = weights[src] @ fields[src][:, left]
                target = fields[dst][:, right]
                messages[dst] = messages[dst] + self.field_weight * (expected @ target.T) / target.size(-1)
            if reads:
                shared = torch.stack(reads).mean(0)
                states = [self.context(shared + read, state) for read, state in zip(reads, states, strict=True)]
        summary = torch.stack(states).mean(0) if states else self.intent + root
        return logits, self.stop(summary).squeeze(-1)


def rule_inputs(catalog, memory, domains, rid):
    """Materialize each typed domain once per role, retaining old non-anchor ports."""
    atoms = catalog.atoms[rid]
    ids = [domains.rows.get(table, domains.empty) for table, _ in atoms]
    if any(not len(domain) for domain in ids):
        return None
    fresh = [(domains.versions[domain] >= memory.rules[rid]).to(memory.keys.dtype) for domain in ids]
    if atoms and catalog.seminaive[rid] and not any(mask.any().item() for mask in fresh):
        return None
    links = [(src, left, dst, right) for src in range(len(atoms)) for dst in range(len(atoms))
             if src != dst for left, right in catalog.field_links[rid, src, dst]]
    inputs = (memory.nodes[catalog.roots['generated', rid]], [memory.nodes[node] for _, node in atoms],
              [memory.keys[d] for d in ids], [memory.fields[d] for d in ids], fresh, links)
    return inputs, ids


def named_requests(rid, history, mem, domains, logits, stop):
    """No prefix selection. The native receiver owns visibility, guard and delta checks."""
    addresses = [domain[score.argmax(-1)].tolist() for domain, score in zip(domains, logits, strict=True)]
    for proposal in (stop < 0).nonzero().flatten().tolist():
        parents = []
        for chosen in addresses:
            port = mem.ports[chosen[proposal]]
            alias, op = port.address
            parents.append(dict(address=dict(token=history.inverse[alias], op=op), version=port.version))
        yield dict(run=history.run, rule=rid, parents=parents)
