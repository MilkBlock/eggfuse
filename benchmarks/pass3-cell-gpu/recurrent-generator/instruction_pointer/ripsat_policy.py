"""One compositional scorer for a catalog of variable-size, typed Cell instruction graphs."""
import math

import numpy as np
import torch
from torch import nn

from actor import rotate, row_features


def positional(width, index):
    return rotate(torch.ones(1,width),torch.tensor([index]))[0]


class GraphBank:
    """Store shared static vectors once. Gather a dense tensor only for a model batch."""

    def __init__(self, layouts, catalog, nodes):
        count = len(layouts)
        length = max(map(len, layouts))
        fan = max(len(wires) for layout in layouts for _, _, wires in layout)
        step_ids = np.zeros((count, length), dtype=np.int32)
        edge_ids = np.zeros((count, length, fan), dtype=np.int32)
        parents = np.zeros_like(edge_ids)
        step_vectors = [nodes.new_zeros(nodes.shape[1])]
        edge_vectors = [torch.zeros_like(step_vectors[0])]
        step_keys = {}
        edge_keys = {}
        positions = {}

        def position(k):
            if k not in positions:
                positions[k] = positional(nodes.shape[1], k)
            return positions[k]

        for i, layout in enumerate(layouts):
            for j, (rid, group, wires) in enumerate(layout):
                template = 'generated', rid
                root = catalog.roots[template]
                key = root, group
                if key not in step_keys:
                    step_keys[key] = len(step_vectors)
                    step_vectors.append(nodes[root] + position(group))
                step_ids[i, j] = step_keys[key]
                inputs = catalog.inputs[template]
                if len(wires) != len(inputs):
                    raise ValueError('wrong template arity')
                for role, (owner, slot) in enumerate(wires):
                    if slot < 0 or owner < -1 or owner >= j:
                        raise ValueError('invalid source in Cell wiring')
                    pc = None
                    if owner >= 0:
                        pc = catalog.outputs[('generated', layout[owner][0]), slot]
                        parents[i, j, role] = owner + 1
                    atom = inputs[role]
                    key = atom, role, pc, slot
                    if key not in edge_keys:
                        source = position(slot) if pc is None else nodes[pc] + position(slot)
                        vector = rotate((source + nodes[atom])[None], torch.tensor([role]))[0]
                        edge_keys[key] = len(edge_vectors)
                        edge_vectors.append(vector)
                    edge_ids[i, j, role] = edge_keys[key]
        self.step_ids = torch.from_numpy(step_ids)
        self.edge_ids = torch.from_numpy(edge_ids)
        self.parents = torch.from_numpy(parents)
        self.steps = torch.stack(step_vectors)
        self.edges = torch.stack(edge_vectors)

    def batch(self, indices, device):
        steps = self.step_ids[indices].long()
        edges = self.edge_ids[indices].long()
        batch = (self.steps[steps], steps != 0, self.edges[edges],
                 self.parents[indices].long(), edges != 0)
        return tuple(t.to(device) for t in batch)

    def encode(self, model, batch_size=256):
        device = next(model.parameters()).device
        return torch.cat([model.encode(self.batch(slice(i, i + batch_size), device))
                          for i in range(0, len(self.step_ids), batch_size)])


class CellScorer(nn.Module):
    def __init__(self,width):
        super().__init__()
        self.step=nn.Linear(width,width)
        self.edge=nn.Linear(width,width)
        self.message=nn.Linear(width,width,bias=False)
        self.context=nn.Linear(width,width)
        self.head=nn.Sequential(nn.Linear(3*width,width),nn.Tanh(),nn.Linear(width,2))

    def encode(self,graphs):
        steps,valid,edges,incoming,used=graphs
        n,length,width=steps.shape
        states=[steps.new_zeros(n,width)]
        ids=torch.arange(n,device=steps.device)[:,None]
        for j in range(length):
            parents=torch.stack(states,1)[ids,incoming[:,j]]
            messages=(self.edge(edges[:,j])+self.message(parents)).tanh()*used[:,j,:,None]
            x=self.step(steps[:,j])+messages.sum(1)/used[:,j].sum(1).clamp_min(1)[:,None].sqrt()
            states.append(x.tanh()*valid[:,j,None])
        return torch.stack(states[1:],1).sum(1)/valid.sum(1)[:,None].sqrt()

    def forward(self,context,templates):
        context=self.context(context).tanh()
        return self.head(torch.cat((context,templates,context*templates),dim=-1))


def root_context(hashes,width):
    # Encode only the named parents already supplied by the root Actor.
    if not hashes:
        return torch.zeros(width)
    values=row_features([tuple(row) for row in hashes],width,'cpu')
    return rotate(values,torch.arange(len(values))).sum(0)/math.sqrt(len(values))
