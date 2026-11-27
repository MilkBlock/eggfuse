"""Embedding-only interventions. The same frozen C reader consumes every representation."""

import torch

from actor import rotate
from cell_kv_model import CellKV


class TokenEmbedding(CellKV):
    def __init__(self, a, variant, initial):
        super().__init__(a, "C", True)
        self.variant = variant
        self.load_state_dict(initial)
        self.requires_grad_(False)
        for layer in [
            self.actor.static,
            self.actor.msg,
            self.actor.update,
            self.graph.step,
            self.graph.edge,
            self.graph.message,
            self.actor.dynamic,
            self.actor.age,
        ]:
            layer.requires_grad_(True)

    def instance_embedding(self, w, ports, positions, siblings, group, source, value):
        if not siblings or self.variant == "current":
            return super().instance_embedding(
                w, ports, positions, siblings, group, source, value
            )
        if self.variant == "structure":
            owners = torch.stack([source[ix[0]] for ix in siblings]).tanh()
            return owners, owners[group]
        if self.variant == "mixed":
            owners, _ = super().instance_embedding(
                w, ports, positions, siblings, group, source, value
            )
            return owners, owners[group]
        if self.variant != "interface":
            raise ValueError(self.variant)
        # Read named input refs of this instance only. Keep holes in role numbering.
        nodes = self.cache[0]
        boundary = [None] * len(ports)
        owners = []
        for ix in siblings:
            first = int(ix[0])
            _, owner, tid, _, _, _, parents = ports[first]
            entry = torch.zeros_like(value[first])
            if tid >= 0:
                root = w.layouts[tid][0][0]
                for j, parent in enumerate(parents):
                    if parent in positions:
                        role = nodes[w.cat.inputs["generated", root][j]]
                        entry = (
                            entry
                            + rotate(
                                (value[positions[parent]] + role)[None],
                                torch.tensor([j]),
                            )[0]
                        )
                entry = entry / max(len(parents), 1)
            for i in ix.tolist():
                (uid, op, _), *_ = ports[i]
                code = value[i]
                if tid >= 0:
                    step = 0 if uid == owner else -1
                    rid = w.layouts[tid][step][0]
                    output = w.cat.outputs.get((("generated", rid), op))
                    if output is not None:
                        code = code + nodes[output]
                boundary[i] = (code + entry + source[i]).tanh()
            owners.append((source[first] + entry + value[ix].mean(0)).tanh())
        return torch.stack(owners), torch.stack(boundary)
