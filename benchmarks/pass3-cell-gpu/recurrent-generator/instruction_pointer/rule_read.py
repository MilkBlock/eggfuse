"""Rule selection over a sealed Cell port memory. Parent decoding stays in the Actor."""
import math

import torch
from torch import nn

from actor import InstructionActor, ints


class RuleReadActor(InstructionActor):
    def __init__(self, mode, field_pointer=True, mask_anchors=False):
        super().__init__(field_pointer=field_pointer)
        if mode not in ('global', 'typed'):
            raise ValueError('unknown rule read mode')
        self.read_mode = mode
        self.mask_anchors = mask_anchors
        width = self.width
        self.read_key = nn.Linear(3 * width + 2, width)
        self.read_query = nn.Linear(width, width)
        self.read_bias = nn.Linear(width, 1)
        nn.init.zeros_(self.read_query.weight)
        nn.init.zeros_(self.read_query.bias)
        nn.init.zeros_(self.read_bias.weight)
        nn.init.zeros_(self.read_bias.bias)

    def memory(self, catalog, snapshot, nodes=None, issued_latents=None):
        mem = super().memory(catalog, snapshot, nodes, issued_latents)
        mem.rule_inputs = self.rule_inputs(catalog, mem)
        if self.mask_anchors:
            mem.rule_support = self.anchor_support(catalog, mem)
        return mem

    @staticmethod
    def anchor_support(catalog, mem):
        """Only the union of single-atom delta domains. No tests across parents."""
        latest = {}
        for port in mem.ports:
            latest[port.table] = max(latest.get(port.table, -1), port.version)
        supported = []
        for rid, wm in mem.rules.items():
            atoms = catalog.atoms[rid]
            # Native proof epochs start at zero for a zero-table-parent request.
            newest = max((latest.get(table, -1) for table, _ in atoms), default=0)
            minimum = wm if catalog.seminaive[rid] else 0
            supported.append(newest >= minimum)
        return torch.tensor(supported, device=mem.nodes.device, dtype=torch.bool)

    def rule_inputs(self, catalog, mem):
        nodes, keys = mem.nodes, mem.keys
        rules = list(mem.rules)
        roots = nodes[ints(nodes, [catalog.roots['generated', r] for r in rules])]
        width = self.width
        if not rules:
            return nodes.new_empty((0, 3 * width + 2))
        if self.read_mode == 'global':
            mean = keys.mean(0) if len(keys) else nodes.new_zeros(width)
            pool = mean.expand(len(rules), width)
            count = nodes.new_full((len(rules), 2), math.log1p(len(keys)))
            return torch.cat((roots, pool, pool, count), -1)

        tables = ints(nodes, [p.table for p in mem.ports])
        versions = ints(nodes, [p.version for p in mem.ports])
        def pool(ids, values):
            size = len(catalog.tables)
            counts = nodes.new_zeros(size).index_add_(0, ids, nodes.new_ones(len(ids)))
            sums = nodes.new_zeros((size, width)).index_add_(0, ids, values)
            return sums / counts.clamp_min(1)[:, None], counts.log1p()

        visible = pool(tables, keys)
        atoms = [(i, t, role) for i, r in enumerate(rules) for t, role in catalog.atoms[r]]
        summary = nodes.new_zeros((len(rules), 2 * width + 2))
        if atoms:
            which, table, role = ints(nodes, atoms).T
            fresh = torch.zeros_like(visible[0][table])
            counts = torch.zeros_like(visible[1][table])
            groups = {}
            for j, (i, _, _) in enumerate(atoms):
                rid = rules[i]
                wm = mem.rules[rid] if catalog.seminaive[rid] else None
                groups.setdefault(wm, []).append(j)
            for wm, js in groups.items():
                idx = ints(nodes, js)
                if wm is None:
                    means, sizes = visible
                else:
                    eligible = versions >= wm
                    means, sizes = pool(tables[eligible], keys[eligible])
                fresh[idx] = means[table[idx]]
                counts[idx] = sizes[table[idx]]
            roles = nodes[role].tanh()
            rows = torch.cat((roles * visible[0][table], roles * fresh,
                              visible[1][table, None], counts[:, None]), -1)
            summary.index_add_(0, which, rows)
            arity = [max(1, len(catalog.atoms[r])) for r in rules]
            summary = summary / nodes.new_tensor(arity)[:, None]
        return torch.cat((roots, summary), -1)

    def correction(self, features, lanes):
        key = self.read_key(features).tanh()
        query = self.read_query(lanes)
        return query @ key.transpose(-1, -2) / math.sqrt(self.width) + self.read_bias(key).transpose(-1, -2)

    def action_logits(self, catalog, memory, h, rules):
        _, _, logits = super().action_logits(catalog, memory, h, rules)
        residual = self.correction(memory.rule_inputs, h.unsqueeze(0)).squeeze(0)
        scores = logits[1:] + residual
        if memory.rule_support is not None:
            scores = scores.masked_fill(~memory.rule_support, -torch.inf)
        return h, rules, torch.cat((logits[:1], scores))


def load_actor(weights, field_pointer):
    state = torch.load(weights, map_location='cpu', weights_only=True) if weights else None
    if state is not None and state.get('format') == 'parallel-anchor-v1':
        from anchor_set import AnchorSetActor
        actor = AnchorSetActor(state['vocabulary'],state['names'])
        actor.load_state_dict(state['parameters'])
    elif state is not None and state.get('format') == 'parent-history-v1':
        from parent_actor import ParentActor
        actor = ParentActor(field_pointer)
        actor.load_state_dict(state['parameters'])
    elif state is not None and state.get('format') == 'wave-receipt-v1':
        from receipt_actor import ReceiptActor
        actor = ReceiptActor(field_pointer)
        actor.load_state_dict(state['parameters'])
    elif state is not None and state.get('format') == 'sequence-actor-v1':
        from sequence_actor import SequenceActor
        actor = SequenceActor(field_pointer)
        actor.load_state_dict(state['parameters'])
    elif state is not None and state.get('format') == 'rule-read-v1':
        actor = RuleReadActor(state['read_mode'], field_pointer, state.get('mask_anchors', False))
        actor.load_state_dict(state['parameters'])
    else:
        actor = InstructionActor(field_pointer=field_pointer)
        if state is not None:
            actor.load_state_dict(state)
    return actor.eval()
