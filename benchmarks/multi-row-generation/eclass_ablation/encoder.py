"""Gated, template-local equivalence views for a per-port PyTorch GNN.

The four bank entries correspond to (pre/post, producer committed for this
instance). All classes are anonymous. The output always follows the original
physical port order, even when two ports are in the same certified class.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

import torch
from torch import nn
import torch.nn.functional as F


ARMS = ('explicit', 'singleton', 'pairwise', 'incidence')
CLASS_KIND = '__anon_template_class__'


def vocabulary(values):
    return {value: i + 1 for i, value in enumerate(sorted(set(values)))}


def layout_digest(template):
    payload = {key: template.get(key) for key in ('id', 'version', 'template_version', 'schema', 'source_sha256', 'graph', 'ports', 'certificates')}
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def certified_partition(template, stage, committed):
    """Closure of admitted local operations. Class indices are absent from all features."""
    ports = template['ports']
    nodes = template['graph']['nodes']
    ids = [port['node'] for port in ports]
    if not ports or len(set(ids)) != len(ids) or any(type(i) is not int or not 0 <= i < len(nodes) for i in ids):
        raise ValueError('ports must map injectively to graph nodes')
    parent = list(range(len(ports)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for cert in template['certificates']:
        left, right = cert['left_port'], cert['right_port']
        if any(type(i) is not int or not 0 <= i < len(ports) for i in (left, right)):
            raise ValueError('certificate must refer to local port indices')
        if cert['guard'] != 'producer_committed' or cert.get('scope', 'template') not in ('template', 'template_local'):
            raise ValueError('expected a compiler-admitted local producer commitment')
        if cert.get('operation') is None or type(cert['visible_from_stage']) is not int or cert['visible_from_stage'] < 1:
            raise ValueError('certificate requires its executed operation and earliest post-union stage')
        # A graph node may use a coarse display sort. Prefer the precise physical
        # port sort from the compiled port declaration whenever it is available.
        sorts = [ports[i].get('sort', nodes[ids[i]]['sort']) for i in (left, right)]
        if sorts[0] != sorts[1] or sorts[0] != cert['sort']:
            raise ValueError('certificate endpoints must have the certified sort')
        if committed and stage >= cert['visible_from_stage']:
            parent[root(right)] = root(left)
    groups = {}
    for i in range(len(ports)):
        groups.setdefault(root(i), []).append(i)
    return tuple(tuple(members) for members in groups.values())


@dataclass
class PortView:
    local: torch.Tensor
    adjacency: torch.Tensor          # structural relations followed by physical alias links
    degree: torch.Tensor             # [node, relation] incl. logical degrees in matched mode
    port_nodes: torch.Tensor         # original stable port order -> graph node
    membership: torch.Tensor | None  # matched incidence only: [class, original port]
    stats: dict


@dataclass
class StateBank:
    views: tuple
    indices: tuple                   # 00, 01, 10, 11 -> unique view index
    signature: tuple


class EClassSchema:
    """Fit base roles on training templates and reserve the same alias features in every arm."""

    def __init__(self, training):
        nodes = [node for template in training for node in template['graph']['nodes']]
        self.kinds = vocabulary([str(n['kind']) for n in nodes] + [CLASS_KIND])
        self.sorts = vocabulary(str(n['sort']) for n in nodes)
        self.ordinals = vocabulary(int(n['ordinal']) for n in nodes)
        self.relations = vocabulary((direction, str(label)) for template in training
                                    for _, label, _ in template['graph']['edges'] for direction in ('in', 'out'))
        self.local_width = len(self.kinds) + len(self.sorts) + len(self.ordinals) + 3
        self.relation_count = len(self.relations) + 2  # unknown structural type and reserved alias type
        vocabulary_key = [sorted(self.kinds.items()), sorted(self.sorts.items()),
                          sorted(self.ordinals.items()), sorted(self.relations.items())]
        self.signature = sha256(json.dumps(vocabulary_key).encode()).hexdigest()

    def _local(self, nodes):
        features = []
        for key, mapping in (('kind', self.kinds), ('sort', self.sorts), ('ordinal', self.ordinals)):
            values = [mapping.get(node[key], 0) for node in nodes]
            features.append(F.one_hot(torch.tensor(values), len(mapping) + 1).float())
        return torch.cat(features, -1)

    def _pack(self, template, arm, groups, device, transport):
        graph = template['graph']
        nodes = [dict(kind=str(n['kind']), sort=str(n['sort']), ordinal=int(n['ordinal'])) for n in graph['nodes']]
        num_base = len(nodes)
        port_indices = [p['node'] for p in template['ports']]
        pair = arm == 'pairwise'
        incidence = arm in ('singleton', 'incidence')
        physical = transport == 'physical'
        if incidence and physical:
            for group in groups:
                # Unknown ordinal represents the absence of a position. All class
                # nodes of the same sort receive exactly the same initial local role.
                nodes.append(dict(kind=CLASS_KIND, sort=nodes[port_indices[group[0]]]['sort'], ordinal=None))
        count = len(nodes)
        edges = torch.zeros(self.relation_count, count, count)
        for source, label, target in graph['edges']:
            if not 0 <= source < num_base or not 0 <= target < num_base:
                raise ValueError('structural edge endpoint is outside the base graph')
            edges[self.relations.get(('in', str(label)), 0), target, source] += 1
            edges[self.relations.get(('out', str(label)), 0), source, target] += 1
        links = edges[-1]
        membership = None
        if incidence and not physical:
            membership = torch.zeros(len(groups), len(port_indices))
        for class_no, local_ports in enumerate(groups):
            members = [port_indices[i] for i in local_ports]
            if pair:
                for node in members:
                    for peer in members:
                        if peer != node:
                            links[node, peer] = 1
            elif incidence and physical:
                class_node = num_base + class_no
                links[class_node, members] = 1
                links[members, class_node] = 1
            elif membership is not None:
                membership[class_no, list(local_ports)] = 1
        degrees = edges.sum(-1)
        adjacency = edges / degrees.clamp_min(1)[..., None]
        if membership is not None:
            # Matched-hop transport carries peer means excluding self. Compute
            # peer degrees through membership without constructing a dense clique.
            degrees[-1, port_indices] = membership.T @ (membership.sum(1) - 1)
        stats = dict(base_nodes=num_base, class_nodes=count - num_base, physical_ports=len(port_indices),
                     base_directed_messages=2 * len(graph['edges']),
                     alias_directed_messages=int(links.sum().item()) if membership is None
                     else 2 * int(membership.sum().item()),
                     nonsingleton_classes=sum(len(group) > 1 for group in groups))
        return PortView(self._local(nodes).to(device), adjacency.to(device), degrees.T.contiguous().to(device),
                        torch.tensor(port_indices, device=device),
                        None if membership is None else membership.to(device), stats)

    def bank(self, template, arm, device, transport='physical'):
        if arm not in ARMS or transport not in ('physical', 'matched'):
            raise ValueError('unknown graph arm or transport mode')
        if transport == 'matched' and arm not in ('pairwise', 'incidence'):
            raise ValueError('matched transport compares the two certified representations')
        singletons = tuple((i,) for i in range(len(template['ports'])))
        groups = []
        indices = []
        for phase in (0, 1):
            for committed in (False, True):
                partition = certified_partition(template, phase, committed)
                view = singletons if arm in ('explicit', 'singleton') else partition
                if view not in groups:
                    groups.append(view)
                indices.append(groups.index(view))
        views = tuple(self._pack(template, arm, partition, device, transport) for partition in groups)
        return StateBank(views, tuple(indices), (self.signature, layout_digest(template), arm, transport, str(device)))


def permute_class_storage(graph, order=None):
    """Rename anonymous class nodes while leaving every physical port address intact."""
    size = graph.membership.shape[0] if graph.membership is not None else graph.stats['class_nodes']
    if size <= 1:
        return graph
    device = graph.local.device
    if order is None:
        order = torch.randperm(size, device=device)
    if graph.membership is not None:
        return PortView(graph.local, graph.adjacency, graph.degree, graph.port_nodes,
                        graph.membership.index_select(0, order), graph.stats)
    base = graph.stats['base_nodes']
    permutation = torch.cat((torch.arange(base, device=device), base + order))
    return PortView(graph.local.index_select(0, permutation),
                    graph.adjacency.index_select(1, permutation).index_select(2, permutation),
                    graph.degree.index_select(0, permutation), graph.port_nodes, None, graph.stats)


class PortLayer(nn.Module):
    def __init__(self, width, relation_count):
        super().__init__()
        self.relation = nn.Parameter(torch.randn(relation_count, width) * 0.05)
        self.update = nn.Sequential(nn.Linear(2 * width, width), nn.GELU(), nn.Linear(width, width))
        self.norm = nn.LayerNorm(width)

    def forward(self, hidden, graph):
        messages = graph.adjacency @ hidden
        if graph.membership is not None:
            # Reduce to an anonymous class once, then broadcast to its ports.
            # The net result matches a direct peer-edge mean in one logical hop.
            h = hidden.index_select(0, graph.port_nodes)
            total = graph.membership @ h
            peer_sum = graph.membership.T @ total - h
            degree = graph.degree.index_select(0, graph.port_nodes)[:, -1:]
            alias = torch.zeros_like(hidden).index_copy(0, graph.port_nodes, peer_sum / degree.clamp_min(1))
            messages = torch.cat((messages[:-1], alias[None]), dim=0)
        gate = graph.degree.T.clamp(max=1)[..., None] * self.relation[:, None, :]
        incoming = (messages * gate).sum(0)
        return self.norm(hidden + self.update(torch.cat((hidden, incoming), dim=-1)))


class EClassEncoder(nn.Module):
    def __init__(self, schema, width=32, rounds=2):
        super().__init__()
        self.rounds = rounds
        self.direct = nn.Linear(schema.local_width, width)
        self.role = nn.Linear(schema.local_width + schema.relation_count, width)
        self.layers = nn.ModuleList(PortLayer(width, schema.relation_count) for _ in range(rounds))
        self.out = nn.Sequential(nn.Linear(2 * width, width), nn.LayerNorm(width))
        self._frozen = {}

    def forward(self, graph):
        hidden = self.role(torch.cat((graph.local, graph.degree.log1p()), dim=-1))
        for layer in self.layers:
            hidden = layer(hidden, graph)
        direct = self.direct(graph.local.index_select(0, graph.port_nodes))
        return self.out(torch.cat((direct, hidden.index_select(0, graph.port_nodes)), dim=-1))

    def encode_bank(self, bank):
        unique = [self(permute_class_storage(view) if self.training else view) for view in bank.views]
        return torch.stack([unique[i] for i in bank.indices], dim=0)

    def frozen_bank(self, bank):
        """Cache all four legal state choices per template and frozen parameter revision."""
        if self.training or torch.is_grad_enabled():
            raise RuntimeError('frozen embedding cache requires eval and no gradient tracking')
        parameters = tuple(self.parameters())
        if any(torch.is_inference(p) for p in parameters):
            raise RuntimeError('construct and move encoder parameters outside inference_mode for versioned caching')
        version = tuple((id(p), p._version, p.device, p.dtype) for p in parameters)
        key = (bank.signature, self.rounds)
        entry = self._frozen.get(key)
        if entry is None or entry[0] != version:
            entry = (version, self.encode_bank(bank))
            self._frozen[key] = entry
        return entry[1]


def select_state(table, phase, committed):
    """GPU gather for each local instance, preserving the ordered physical ports."""
    phase = torch.as_tensor(phase, device=table.device)
    committed = torch.as_tensor(committed, device=table.device)
    if phase.is_floating_point() or committed.is_floating_point():
        raise ValueError('expected discrete phase and local producer receipt')
    phase, committed = torch.broadcast_tensors(phase, committed)
    valid = ((phase == 0) | (phase == 1)) & ((committed == 0) | (committed == 1))
    code = torch.where(valid, 2 * phase.long() + committed.long(), 4)
    return table.index_select(0, code.reshape(-1)).reshape(*code.shape, *table.shape[1:])
