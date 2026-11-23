"""A shared instruction pointer for initial, issued and native repair ports."""
from dataclasses import dataclass
import math

import numpy as np
import torch
from torch import nn

from catalog import KINDS


def ints(like, seq):
    return torch.tensor(seq, dtype=torch.long, device=like.device)


def rotate(values, positions):
    half = values.shape[-1] // 2
    freq = torch.exp(torch.arange(half, device=values.device) * (-math.log(10000) / half))
    phase = positions.to(values.dtype).unsqueeze(-1) * freq
    a, b = values[..., ::2], values[..., 1::2]
    return torch.stack((a * phase.cos() - b * phase.sin(),
                        a * phase.sin() + b * phase.cos()), dim=-1).flatten(-2)


def row_features(rows, width, device):
    """Encode port fields independently of every other port. Input order is significant."""
    # Encode each distinct input row once, then gather in original port order.
    # No rows are removed from either the memory or the pointer action space.
    unique = list(dict.fromkeys(rows))
    row_ids = {row:i for i,row in enumerate(unique)}
    values = np.zeros((len(unique),width), dtype=np.float64)
    for col in range(max(map(len,unique),default=0)):
        present = [i for i,row in enumerate(unique) if col < len(row)]
        bits = np.array([unique[i][col] for i in present],dtype=np.uint64)
        shifts = (np.arange(width,dtype=np.uint64)+7*col)%64
        signed = 2.*((bits[:,None] >> shifts) & 1)-1.
        values[present] += signed / (1+col)
    indices = np.fromiter((row_ids[row] for row in rows),dtype=np.intp,count=len(rows))
    return torch.from_numpy(values.astype(np.float32)[indices]).to(device)


@dataclass
class Memory:
    nodes: torch.Tensor
    keys: torch.Tensor
    ports: list
    rules: dict
    fields: torch.Tensor | None = None


class InstructionActor(nn.Module):
    def __init__(self, width=32, lanes=4, field_pointer=False):
        super().__init__()
        if width % 2:
            raise ValueError('rotary width must be even')
        self.width = width
        self.field_pointer = field_pointer
        self.static = nn.Embedding(8192, width)
        self.msg = nn.Linear(width, width, bias=False)
        self.update = nn.Linear(width, width)
        self.kind = nn.Embedding(len(KINDS), width)
        self.dynamic = nn.Linear(width, width, bias=False)
        self.input_content = nn.Linear(width, width, bias=False)
        self.input_role = nn.Linear(width, width)
        self.latent = nn.Linear(width, width, bias=False)
        self.age = nn.Linear(2, width, bias=False)
        self.lanes = nn.Embedding(lanes, width)
        self.next_read = nn.GRUCell(width, width)
        self.query = nn.Linear(width, width)
        self.stop = nn.Linear(width, 1)

    def template_graph(self, catalog):
        device = self.static.weight
        h = self.static(ints(device, catalog.nodes))
        if not catalog.edges:
            return h
        src, dst, role = ints(device, catalog.edges).T
        count = h.new_zeros(len(h)).index_add(0, dst, h.new_ones(len(dst))).clamp_min(1)
        for _ in range(2):
            messages = rotate(self.msg(h[src]), role)
            acc = torch.zeros_like(h).index_add(0, dst, messages)
            h = (h + self.update(acc / count[:, None])).tanh()
        return h

    def memory(self, catalog, snapshot, nodes=None, issued_latents=None):
        nodes = self.template_graph(catalog) if nodes is None else nodes
        ports = snapshot.ports
        if not ports:
            return Memory(nodes, nodes.new_empty((0, self.width)), [], snapshot.rules)
        idx = lambda seq: ints(nodes, seq)
        pc = idx([p.address[1] for p in ports])
        base = nodes[idx([p.root for p in ports])] + self.kind(idx([KINDS.index(p.kind) for p in ports]))
        feature = lambda rows: row_features(rows, self.width, nodes.device)
        base = base + self.dynamic(feature([p.hashes for p in ports]))
        delta = [[math.log1p(snapshot.epoch - p.version), float(p.forwarded)] for p in ports]
        base = base + self.age(nodes.new_tensor(delta))
        sources = [(i, role, parent) for i,p in enumerate(ports) for role,parent in p.inputs]
        if sources:
            owners = idx([i for i, _, _ in sources])
            parent = [v for _, _, v in sources]
            role = self.input_role(nodes[idx([r for _, r, _ in sources])]).tanh()
            source = rotate(nodes[idx([v.node for v in parent])], idx([v.pc for v in parent]))
            content = self.input_content(source + self.dynamic(feature([v.hashes for v in parent])))
            contributions = content * role
            base = base.index_add(0, owners, contributions)
        if issued_latents:
            selected = [(i, issued_latents[p.address[0]]) for i,p in enumerate(ports)
                        if p.kind == 'generated' and p.address[0] in issued_latents]
            if selected:
                base = base.index_add(0, idx([i for i,_ in selected]),
                                      self.latent(torch.stack([v for _,v in selected])))
        keys = (nodes[idx([p.node for p in ports])] + rotate(base, pc)).tanh()
        fields = None
        if self.field_pointer:
            # A port is encoded in isolation. Keep the columns separate so a
            # subsequent pointer can read a selected field without GRU compression.
            arity = max(len(p.hashes) for p in ports)
            raw = [[list(v.to_bytes(8, "little")) for v in p.hashes] +
                   [[0]*8]*(arity-len(p.hashes)) for p in ports]
            octets = nodes.new_tensor(raw, dtype=torch.int32)
            shifts = torch.arange(8, dtype=torch.int32, device=nodes.device)
            fields = (((octets[..., None] >> shifts) & 1).flatten(-2).to(nodes.dtype)*2-1)
        return Memory(nodes, keys, ports, snapshot.rules, fields)

    def actions(self, catalog, memory, lane):
        rules = list(memory.rules)
        h = self.lanes.weight[lane]
        if len(memory.keys):
            h = self.next_read(memory.keys.mean(0), h)
        return self.action_logits(catalog,memory,h,rules)

    def resume_lane(self,catalog,memory,h,rules,issued):
        return self.action_logits(catalog,memory,self.next_read(issued,h),rules)

    def action_logits(self,catalog,memory,h,rules):
        roots = ints(h, [catalog.roots['generated', rid] for rid in rules])
        logits = torch.cat((self.stop(h), memory.nodes[roots] @ self.query(h) / math.sqrt(self.width)))
        return h, rules, logits

    def related_fields(self,catalog,mem,rid,selected,role,logits):
        if mem.fields is not None:
            for previous,index in selected:
                for source,target in catalog.field_links[rid,previous,role]:
                    query = mem.fields[index,source]
                    logits = logits + (mem.fields[:,target] @ query) / math.sqrt(query.numel())
        return logits

    def references(self, catalog, mem, h, rid, teacher=None):
        """Select a fresh anchor across all roles, then name every other parent in order."""
        atoms = catalog.atoms[rid]
        if not atoms:
            return (), []
        where = {p.address:i for i,p in enumerate(mem.ports)} if teacher is not None else {}
        fresh = catalog.seminaive[rid]
        setup = mem.nodes[catalog.roots['generated',rid]]
        h = self.next_read(setup, h)
        roles = mem.nodes[ints(h,[node for _,node in atoms])]
        scores = self.query(h + roles) @ mem.keys.T / math.sqrt(self.width)
        eligible = torch.tensor([[p.table == table and (not fresh or p.version >= mem.rules[rid])
                                  for p in mem.ports] for table,_ in atoms], device=h.device,
                                dtype=torch.bool)
        if not mem.ports or not eligible.any().item():
            return None, []
        logits = scores.masked_fill(~eligible, -torch.inf).flatten()
        losses = []
        if teacher is None:
            pick = int(logits.argmax())
        else:
            indices = [where[a] for a in teacher]
            valid = [i*len(mem.ports)+j for i,j in enumerate(indices) if eligible[i,j].item()]
            if not valid:
                raise ValueError('no legal delta anchor in teacher proof')
            logp = logits.log_softmax(0)
            losses.append(-torch.logsumexp(logp[ints(h,valid)],0))
            pick = max(valid, key=lambda i: float(logits[i].detach()))
        anchor, first = divmod(pick, len(mem.ports))
        out = [None]*len(atoms)
        out[anchor] = mem.ports[first].address
        h = self.next_read(mem.keys[first]+roles[anchor],h)
        selected = [(anchor, first)]
        for i,(table,_) in enumerate(atoms):
            if i == anchor:
                continue
            mask = torch.tensor([p.table == table for p in mem.ports], device=h.device)
            if not mask.any().item():
                return None, []
            logits = (mem.keys @ self.query(h+roles[i]) / math.sqrt(self.width)).masked_fill(~mask,-torch.inf)
            logits = self.related_fields(catalog,mem,rid,selected,i,logits)
            j = where[teacher[i]] if teacher is not None else int(logits.argmax())
            if teacher is not None:
                losses.append(-logits.log_softmax(0)[j])
            selected.append((i,j))
            out[i] = mem.ports[j].address
            h = self.next_read(mem.keys[j]+roles[i],h)
        return tuple(out), losses
