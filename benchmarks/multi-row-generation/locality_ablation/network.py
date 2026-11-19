"""Figure 14: one graph-wide bank or owner-local recurrent state and replies."""
from pathlib import Path
import sys

import torch
from torch import nn

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'eclass_ablation'))
from model import AliasSystem, MAKE
from fit import study, digest, device, transfer


def load_producer(schema, seed, root, dev):
    import json
    folder = root / f'pairwise-{seed}'
    path = folder / 'final.pt'
    assert digest(path) == json.loads((folder / 'fit.json').read_text())['weight_sha256']
    model = AliasSystem(schema, seed)
    model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
    return model.eval().to(dev).requires_grad_(False)


@torch.no_grad()
def produce(model, inputs, table):
    a, b, _, port = inputs[:4]
    cond = model.operand[0][None].expand(len(a), -1, -1)
    make, frame = model.decoder._stage(a,b,model.decoder._source(a)+table[0][port.long()],
                                       model.decoder._source(b),cond,MAKE,0,True)
    selected = port.gather(1,make['pointers'][...,0])
    return make, torch.cat((frame,selected[...,None].to(frame.dtype)),-1)


def select_rows(values, indices):
    batch = torch.arange(len(values),device=values.device)[:,None]
    return values[batch, indices.long()]


def read_parent(token, req):
    rows = token[...,50:55].int()
    published = token[...,32:34].argmax(-1).bool()
    matches = (rows[:,None,:,:2] == req[:,:,None,2:4]).all(-1) & published[:,None,:]
    pointer = matches.int().argmax(-1)
    return select_rows(rows,pointer), pointer, matches.any(-1)


def project(picked,pointer,req,live,accepted):
    rows = torch.cat((picked[...,:2],req[...,4:5],picked[...,3:5]),-1)
    req_slot = torch.arange(req.shape[1],device=req.device).expand_as(pointer)
    pointers = torch.stack((pointer,req_slot),-1)
    return dict(active=live.int(),pointers=torch.where(accepted[...,None],pointers,-1),
                rows=torch.where(accepted[...,None],rows,-1))


def certified_read(token,controls,certified_ports):
    """Positive witness for a local template path with at most one external edge."""
    req,ports,phase,committed,external,event_ports=controls
    read_owner,source_owner=req[...,0],req[...,2]
    endpoints=torch.where(external[:,1:2]==torch.arange(2,device=req.device),
                          event_ports[:,0:1],event_ports[:,1:2])
    enabled=(phase>=1) & committed.bool()
    def connected(owner,p,q):
        proved=((p[...,None]==certified_ports).any(-1) & (q[...,None]==certified_ports).any(-1))
        return (p==q) | (select_rows(enabled,owner) & proved)
    read,source=ports.unbind(-1)
    local=connected(read_owner,read,source)
    across=(external[:,0:1].bool() & connected(read_owner,read,select_rows(endpoints,read_owner))
            & connected(source_owner,source,select_rows(endpoints,source_owner)))
    proof=torch.where(read_owner==source_owner,local,across)
    picked,pointer,exists=read_parent(token,req)
    return project(picked,pointer,req,proof & exists,torch.ones_like(exists))


class Coordinator(nn.Module):
    def __init__(self):
        super().__init__()
        self.encode = nn.Sequential(nn.Linear(35,32),nn.Tanh(),nn.Linear(32,16))
        self.update = nn.GRUCell(6,16)
        self.head = nn.Sequential(nn.Linear(40,48),nn.Tanh(),nn.Linear(48,1))

    def forward(self, token, controls, certified_ports, scope, delivery='current'):
        state = self.prepare(token, controls, certified_ports, scope)
        return self.finish(token, controls, certified_ports, state, delivery)

    def prepare(self, token, controls, certified_ports, scope):
        _, _, phase, committed, external, event_ports = controls
        rows = token[...,50:55].int()
        active = token[...,32:34].argmax(-1).bool()
        owners = torch.arange(2,device=token.device)
        cert = lambda ports: (ports[...,None] == certified_ports).any(-1)
        # Two state slots in either arm. An owner's external event input contains
        # only its own endpoint. No runtime class membership is a forward input.
        local_event_port = torch.where(external[:,1:2] == owners,event_ports[:,0:1],event_ports[:,1:2])
        event_present = external[:,0:1].bool().expand_as(local_event_port)
        observation = torch.stack((phase, committed, event_present, event_present & cert(local_event_port),
                                   event_present & (local_event_port == certified_ports[0]),
                                   event_present & (local_event_port == certified_ports[1])), -1).float()
        local = scope == 'local'
        if scope not in ('global','local'):
            raise ValueError(scope)
        states = []
        for owner in (0,1):
            belongs = rows[...,0] == owner
            feature = torch.cat((token[...,:32],belongs[...,None],active[...,None],
                                 cert(token[...,-1].int())[...,None]),-1)
            encoded = self.encode(feature)
            visible = active & belongs if local else active
            pooled = (encoded*visible[...,None]).sum(1)/visible.sum(1,keepdim=True).clamp_min(1)
            updated = self.update(observation[:,owner],pooled)
            states.append(updated)
        return torch.stack(states,1)

    def finish(self, token, controls, certified_ports, state, delivery='current'):
        if delivery not in ('current','drop','stale','mute'):
            raise ValueError(delivery)
        req, req_ports, _, _, external, event_ports = controls
        owners = torch.arange(2,device=token.device)
        local_event_port = torch.where(external[:,1:2] == owners,event_ports[:,0:1],event_ports[:,1:2])
        query_owner, remote_owner = req[...,0],req[...,2]
        crossing = query_owner != remote_owner
        cert = lambda ports: (ports[...,None] == certified_ports).any(-1)
        home = select_rows(state,query_owner)
        # The producing owner selects the requested active Pair and supplies its
        # original physical slot. In this panel the assigned address is explicit.
        picked,pointer,exists = read_parent(token,req)
        version = torch.ones_like(query_owner)
        reply_version = torch.where(crossing,version-1,version) if delivery=='stale' else version
        arrived = (~crossing) if delivery=='drop' else torch.ones_like(crossing)
        accepted = arrived & (reply_version == version)
        peer = select_rows(state,remote_owner) * accepted[...,None]
        if delivery=='mute':
            peer = torch.where(crossing[...,None],0.,peer)
        owner_event = select_rows(local_event_port,query_owner)
        source_event = select_rows(local_event_port,remote_owner)
        local_flags = torch.stack((~crossing,req[...,1]==req[...,3],cert(req_ports[...,0]),
                                   cert(req_ports[...,1]),external[:,0:1].bool().expand_as(crossing),
                                   req_ports[...,0]==owner_event,
                                   (req_ports[...,1]==source_event) & accepted,
                                   (req_ports[...,0]==req_ports[...,1])), -1).float()
        # Inactive events have no observable endpoint.
        flags = torch.cat((local_flags[...,:5],local_flags[...,5:7]*local_flags[...,4:5],
                           local_flags[...,7:]),-1)
        logits = self.head(torch.cat((home,peer,flags),-1)).squeeze(-1)
        live = (logits>=0) & exists & accepted
        return project(picked,pointer,req,live,accepted),logits,~accepted,state
