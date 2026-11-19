"""Single-row consumer of generated records and an instance-scoped port encoding."""
from pathlib import Path
import sys
import torch
from torch import nn

from encoder import EClassEncoder, select_state

BASE = Path(__file__).resolve().parent
sys.path.append(str(BASE.parent / "port_ablation"))
from decoder import OneRowDecoder

WIDTH = 32
MAKE = ((0,0), (0,1), (0,2), (0,3), (1,1))
FINISH = ((0,0), (0,1), (1,4), (0,3), (0,4))
INPUTS = ("a", "b", "requests", "a_port", "request_ports", "phase", "committed", "external", "external_ports")


def feature_row(x):
    """Encode only observed integers. No lookup of an equivalence relation."""
    categories = torch.arange(8, device=x.device)
    return (x.unsqueeze(-1) == categories).float().flatten(-2)


def owner_value(values, owner):
    return values.gather(1, owner.long())


def port_vector(views, owner, port):
    # views[B, instance, physical port, D]. These are template addresses, not
    # equivalence-class addresses. Two equal ports retain distinct input records.
    g = torch.arange(owner.shape[0], device=owner.device)[:, None]
    return views[g, owner.long(), port.long()]


class AliasSystem(nn.Module):
    def __init__(self, schema, seed):
        super().__init__()
        torch.manual_seed(seed)
        self.encoder = EClassEncoder(schema, width=WIDTH, rounds=2)
        self.decoder = OneRowDecoder(WIDTH, 1, True, max_columns=5)
        self.operand = nn.Parameter(torch.randn(2,2,WIDTH) / WIDTH**0.5)
        self.event = nn.Linear(5*8+2*WIDTH,WIDTH)
        self.control = nn.Linear(4,WIDTH)
        self.request_static = nn.Linear(2*WIDTH,WIDTH)
        self.relation = nn.Sequential(nn.Linear(5*WIDTH,WIDTH),nn.GELU(),nn.Linear(WIDTH,2))
        self.relation_feature = nn.Linear(2,WIDTH)
        self.aux = nn.ModuleList(nn.Linear(WIDTH,5*8) for _ in range(2))

    def forward(self, a, b, requests, a_port, request_ports, phase, committed, external, external_ports, table):
        # Publication is best-effort. An incorrect or duplicate physical selection
        # remains in the generated sequence and is charged by the post-hoc verifier.
        ports = self.operand.unsqueeze(0).expand(a.shape[0],-1,-1,-1)
        pre = table[0][a_port.long()]
        make, base_token = self.decoder._stage(a,b,self.decoder._source(a)+pre,self.decoder._source(b),
                                               ports[:,0],MAKE,0,True)
        address = a_port.gather(1,make["pointers"][...,0])
        token = torch.cat((base_token,address[...,None].to(base_token.dtype)),-1)
        finish, relation = self.resume(token,requests,request_ports,phase,committed,external,external_ports,table,ports[:,1])
        return (make,finish),token,relation

    def resume(self, token, requests, request_ports, phase, committed, external, external_ports, table, cond):
        views = select_state(table,phase,committed)
        offset = self.decoder.payload_offset
        rows = token[...,offset:offset+5].long()
        port = token[...,-1].long()
        selected_view = port_vector(views,rows[...,0],port)
        # finish cannot access a, b, or the producer's source features.
        parents = self.decoder.frontier(token[...,:-1])+selected_view+self.decoder.source_position.weight[:8]
        read_owner,src_owner = requests[...,0],requests[...,2]
        read = port_vector(views,read_owner,request_ports[...,0])
        origin = port_vector(views,src_owner,request_ports[...,1])
        # The observed external union event is identical across arms. Any further
        # congruence consequence must be learned, and is never injected here.
        # Read embeddings of the two *observed* event endpoints, not any derived class.
        graph_ids = torch.arange(len(external),device=external.device)
        ends = [views[graph_ids,external[:,col].long(),external_ports[:,k].long()]
                for k,col in enumerate((1,3))]
        event = self.event(torch.cat((feature_row(external),*ends),-1))*external[...,0:1].float()
        controls = torch.stack((owner_value(phase,read_owner),owner_value(committed,read_owner),
                                owner_value(phase,src_owner),owner_value(committed,src_owner)),-1).float()
        query = self.decoder._source(requests)+self.control(controls)+event[:,None,:]
        relation = self.relation(torch.cat((query,read,origin,(read-origin).abs(),read*origin),-1))
        query = query+self.request_static(torch.cat((read,origin),-1))+self.relation_feature(relation)
        finish,_ = self.decoder._stage(rows,requests,parents,query,cond,FINISH,0,True)
        return finish,relation
