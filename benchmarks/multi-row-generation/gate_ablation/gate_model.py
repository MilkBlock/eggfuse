"""Two-row gate in front of the frozen Figure 05 actor's per-slot work."""
import math
from pathlib import Path
import sys

import torch
from torch import nn
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE.parent))
from width_ablation.model import WidthSystem, MAX_CANDIDATES, _select, _decision
from width_ablation.model import _fig20

ROWS = 2
LENGTH = 4
GATE_WIDTH = 8
BACKENDS = ('dense', 'metal_dense', 'metal_skip')
MODES = ('learned', 'all', 'none')


class RowGate(nn.Module):
    """Share one admission head across all positions within the same rule."""
    def __init__(self, dim, token_width):
        super().__init__()
        self.base = nn.Linear(dim, GATE_WIDTH)
        self.history = nn.Linear(token_width, GATE_WIDTH, bias=False)
        self.readout = nn.Linear(GATE_WIDTH, 1)

    def forward(self, prepared, previous):
        # prepared already includes the stage context and physical position.
        return self.readout(torch.tanh(prepared + self.history(previous))).squeeze(-1)


class TorchStage:
    """Compute the original dense actor body, then publish only admitted slots."""
    def __init__(self, decoder, left, right, left_features, right_features, ports, routes):
        self.decoder = decoder
        self.left, self.right, self.left_features = left, right, left_features
        self.left_port, self.right_port = ports[:, 0:1], ports[:, 1:2]
        self.head = decoder.heads[0]
        self.left_keys = self.head.key(left_features).transpose(1, 2)
        self.right_keys = self.head.key(right_features).transpose(1, 2)
        self.wire, self.constants = decoder._routes(left, right, routes)
        context = decoder.pool(torch.cat((left_features.mean(1), right_features.mean(1),
                                          ports[:, 0], ports[:, 1]), -1))
        self.base = context[:, None, None] + decoder.position.weight.reshape(ROWS, LENGTH, decoder.dim)

    def step(self, position, opened, previous, *, audit=False):
        dec = self.decoder
        hidden = torch.tanh(self.base[:,:,position] + dec.history(previous))
        active = dec.active(hidden)
        left_scores = torch.bmm(self.head.query(hidden + self.left_port), self.left_keys) * self.head.scale
        li, lc = _decision(dec, left_scores, MAX_CANDIDATES)
        chosen = _select(self.left_features, li)
        query = hidden + self.right_port + dec.condition_right(chosen)
        right_scores = torch.bmm(self.head.query(query), self.right_keys) * self.head.scale
        ri, rc = _decision(dec, right_scores, MAX_CANDIDATES)
        ai, ac = _decision(dec, active, 2)
        selected = torch.cat((_select(self.left, li), _select(self.right, ri)), -1)
        if self.constants is not None:
            selected = torch.cat((selected, self.constants[:,None].expand(-1,ROWS,-1)), -1)
        payload = selected.index_select(-1, self.wire)
        padded = F.pad(payload.to(hidden.dtype), (0, dec.max_columns-payload.shape[-1]))
        token = torch.cat((hidden, ac, lc, rc, padded), -1)
        # Suppression produces a canonical all-zero token, including hard codes.
        # An open slot whose actor chose null retains its own full generated token.
        def publish(value):
            mask = opened if value.ndim == 2 else opened.unsqueeze(-1)
            return torch.where(mask, value, 0)
        rows = publish(payload)
        result = dict(hidden=publish(hidden), active_logits=publish(active),
                      left_logits=publish(left_scores), right_logits=publish(right_scores),
                      active=publish(ai), pointers=publish(torch.stack((li,ri),-1)), rows=rows,
                      fields=rows[...,2:], pre_active_logits=active,
                      pre_left_logits=left_scores, pre_right_logits=right_scores)
        if audit:
            result['executed'] = torch.ones_like(opened, dtype=torch.int32)
        return result, publish(token)


def gate_choices(logits, mode, threshold_logit, override):
    if mode == 'all':
        policy = torch.ones_like(logits, dtype=torch.bool)
    elif mode == 'none':
        policy = torch.zeros_like(logits, dtype=torch.bool)
    else:
        policy = logits >= threshold_logit
    if override is None:
        return policy
    if override.dtype == torch.bool:
        return override
    if override.dtype not in (torch.int8, torch.int16, torch.int32, torch.int64):
        raise ValueError('integer gate interventions use -1 for policy, 0 for closed, 1 for open')
    # Forcing one decision leaves later policy logits free to react to the
    # intervened token. The override and the policy stay entirely on device.
    return torch.where(override == -1, policy, override == 1)


def stage_override(overrides, stage, batch):
    if overrides is None:
        return None
    value = overrides[stage] if isinstance(overrides, (tuple,list)) else overrides[:,stage]
    if tuple(value.shape) not in ((batch,ROWS,LENGTH), (batch,ROWS*LENGTH)):
        raise ValueError('expected per-stage mask [batch, two rows, four positions] or [batch, eight slots]')
    return value.reshape(batch, ROWS, LENGTH)


class GateSystem(nn.Module):
    """Two gated Runs plus the original WidthSystem available as the ungated reference."""
    def __init__(self, schema, seed):
        super().__init__()
        self.actor = WidthSystem(schema,seed).requires_grad_(False).eval()
        dec = self.actor.decoder
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed + 613)
            self.gates = nn.ModuleList([RowGate(dec.dim,dec.token_width) for _ in range(2)])

    @property
    def encoder(self):
        return self.actor.encoder

    def load_actor(self, state_dict):
        self.actor.load_state_dict(state_dict, strict=True)
        return self

    def train(self, mode=True):
        super().train(mode)
        self.actor.eval()
        return self

    def _stage(self, stage, left, right, left_features, right_features, ports, routes,
               mode, threshold_logit, backend, override, audit):
        decoder = self.actor.decoder
        if backend == 'dense':
            plan = TorchStage(decoder, left, right, left_features, right_features, ports, routes)
        else:
            if __package__:
                from .metal_stage import prepare_metal_stage
            else:
                from metal_stage import prepare_metal_stage
            plan = prepare_metal_stage(decoder,left,right,left_features,right_features,ports,routes,rule_id=0,rows=ROWS)
        gate = self.gates[stage]
        coefficients = gate.base(plan.base)
        previous = coefficients.new_zeros((left.shape[0], ROWS, decoder.token_width))
        outputs = []
        tokens = []
        for position in range(LENGTH):
            logits = gate(coefficients[:,:,position], previous)
            opened = gate_choices(logits,mode,threshold_logit,
                                  None if override is None else override[:,:,position])
            if backend == 'dense':
                row, previous = plan.step(position,opened,previous,audit=audit)
            else:
                row, previous = plan.step(position,opened,previous,physical=backend=='metal_skip',audit=audit)
            row['gate_logits'] = logits
            row['gate_open'] = opened
            outputs.append(row)
            tokens.append(previous)
        packed = {key:torch.stack([s[key] for s in outputs],dim=2).flatten(1,2) for key in outputs[0]}
        return packed, torch.stack(tokens,dim=2).flatten(1,2)

    def forward(self, a, b, requests, a_port, request_ports, phase, committed, external,
                external_ports, table, *, mode='learned', threshold=0.5, backend='dense',
                gate_override=None, audit=False):
        if mode not in MODES or backend not in BACKENDS or not 0 <= threshold <= 1:
            raise ValueError('invalid gate mode, backend or probability threshold')
        if threshold == 0:
            threshold_logit = -math.inf
        elif threshold == 1:
            threshold_logit = math.inf
        else:
            threshold_logit = math.log(threshold / (1-threshold))
        actor = self.actor
        decoder = actor.decoder
        operands = actor.operand.unsqueeze(0).expand(a.shape[0], -1, -1, -1)
        pre = table[0][a_port.long()]
        make, base_token = self._stage(0,a,b,decoder._source(a)+pre,decoder._source(b),
            operands[:,0],_fig20.MAKE,mode,threshold_logit,backend,
            stage_override(gate_override,0,a.shape[0]),audit)
        address = a_port.gather(1,make['pointers'][...,0])
        address = torch.where(make['gate_open'], address, 0)
        token = torch.cat((base_token,address[...,None].to(base_token.dtype)),-1)
        # The consumer takes its accessible parent states from the emitted frontier.
        # Original A/B rows and teacher bindings are absent from this interface.
        finish, rel = self._finish(token,requests,request_ports,phase,committed,external,
            external_ports,table,operands[:,1],mode,threshold_logit,backend,
            stage_override(gate_override,1,a.shape[0]),audit)
        return (make,finish),token,rel

    def _finish(self, token, requests, request_ports, phase, committed, external, external_ports,
                table, operands, mode, threshold_logit, backend, override, audit):
        actor = self.actor
        decoder = actor.decoder
        views = _fig20.select_state(table,phase,committed)
        offset = decoder.payload_offset
        rows = token[...,offset:offset+5].long()
        port = token[...,-1].long()
        selected_view = _fig20.port_vector(views,rows[...,0],port)
        parents = decoder.frontier(token[...,:-1])+selected_view+decoder.source_position.weight[:8]
        read_owner,src_owner = requests[...,0],requests[...,2]
        read = _fig20.port_vector(views,read_owner,request_ports[...,0])
        origin = _fig20.port_vector(views,src_owner,request_ports[...,1])
        graph_ids = torch.arange(len(external),device=external.device)
        ends = [views[graph_ids,external[:,col].long(),external_ports[:,k].long()] for k,col in enumerate((1,3))]
        event = actor.event(torch.cat((_fig20.feature_row(external),*ends),-1))*external[...,0:1].float()
        controls = torch.stack((_fig20.owner_value(phase,read_owner),_fig20.owner_value(committed,read_owner),
                                _fig20.owner_value(phase,src_owner),_fig20.owner_value(committed,src_owner)),-1).float()
        query = decoder._source(requests)+actor.control(controls)+event[:,None,:]
        relation = actor.relation(torch.cat((query,read,origin,(read-origin).abs(),read*origin),-1))
        query = query+actor.request_static(torch.cat((read,origin),-1))+actor.relation_feature(relation)
        finish,_ = self._stage(1,rows,requests,parents,query,operands,_fig20.FINISH,
                               mode,threshold_logit,backend,override,audit)
        return finish,relation
