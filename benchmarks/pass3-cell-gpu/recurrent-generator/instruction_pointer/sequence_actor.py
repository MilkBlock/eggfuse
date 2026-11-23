"""Run-level issuance with one shared stop decision and recurrent named-request feedback."""
import math

import torch
from torch import nn

from actor import ints
from rule_read import RuleReadActor


class SequenceActor(RuleReadActor):
    default_waves = 128

    def __init__(self, field_pointer=True):
        super().__init__('typed', field_pointer, mask_anchors=True)
        width = self.width
        self.sequence_history = nn.GRU(width,width,batch_first=True)
        self.sequence_key = nn.Linear(3 * width + 5,width)
        self.sequence_query = nn.Linear(2 * width,width)
        self.sequence_stop = nn.Linear(2 * width,1)
        self.sequence_missing = nn.Parameter(torch.zeros(width))

    def setup(self, catalog, snapshot, memory):
        rules = list(memory.rules)
        schedule = memory.nodes.new_tensor([
            (math.log1p(memory.rules[r]), math.log1p(snapshot.epoch-memory.rules[r]),
             math.log1p(len(catalog.atoms[r]))) for r in rules]).reshape(-1,3)
        features = torch.cat((memory.rule_inputs,schedule),-1)
        states = [self.actions(catalog,memory,i) for i in range(self.lanes.num_embeddings)]
        return features,torch.stack([s[0] for s in states]),torch.stack([s[2] for s in states])

    def request_key(self, catalog, memory, rid, refs, lookup):
        value = memory.nodes[catalog.roots['generated',rid]]
        if refs is None:
            return value + self.sequence_missing
        for addr in refs:
            value = self.next_read(memory.keys[lookup[addr]],value)
        return value

    def logits(self, keys, past, lanes, base):
        state = torch.cat((past,lanes),-1)
        rule = self.sequence_query(state).tanh() @ keys.transpose(-1,-2) / math.sqrt(self.width)
        return base + torch.cat((self.sequence_stop(state),rule),-1)

    def decisions(self, catalog, snapshot, mem, limit):
        nodes = mem.nodes
        inputs,lanes,base = self.setup(catalog,snapshot,mem)
        keys = self.sequence_key(inputs).tanh()
        by_address = {p.address:i for i,p in enumerate(mem.ports)}
        rules = list(mem.rules)
        past = nodes.new_zeros(1,self.width)
        for _ in range(limit):
            for i in range(len(lanes)):
                scores = self.logits(keys,past,lanes[i:i+1],base[i:i+1]).squeeze(0)
                state = lanes[i],rules,scores
                action = int(scores.argmax())
                if action == 0:
                    yield state,None,None
                    return
                rid = rules[action-1]
                refs,_ = self.references(catalog,mem,lanes[i],rid)
                yield state,rid,refs
                feedback = self.request_key(catalog,mem,rid,refs,by_address)
                _,hidden = self.sequence_history(feedback.view(1,1,-1),past.unsqueeze(0))
                past = hidden[0]

    def decode(self, catalog, snapshot, nodes, limit):
        mem = self.memory(catalog,snapshot,nodes)
        issued = []
        for step,(_,rid,refs) in enumerate(self.decisions(catalog,snapshot,mem,limit)):
            if rid is None:
                return issued,step // self.lanes.num_embeddings + 1,'stop'
            if refs is not None:
                issued.append((rid,refs))
        return issued,limit,'budget'
