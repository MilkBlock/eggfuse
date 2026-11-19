"""Device-owned finite Cell application identities and observation-fenced unions."""
from functools import lru_cache
import json
from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'locality_ablation'))
from network import produce, read_parent, project

READERS={'finish':(0,3),'after_locals':(0,2,3),'each':(0,1,2,3)}
MODES=('immediate','fenced','fused_fenced','late','stale_negative','no_congruence')
COUNTERS=('receipts','nonempty_flushes','explicit_merges','epochs','repair_passes',
          'signature_checks','congruence_merges','expired_negatives','awakened',
          'max_queue','cached_misses','class_reads')


@lru_cache(maxsize=1)
def kernels():
    return torch.mps.compile_shader((HERE/'schedule.metal').read_text())


def device_plan(name,dev):
    p=json.loads((HERE/'plan.json').read_text())['plans'][name]
    public=p['public'][0]+p['public'][1]
    words=[p['vertices'],len(p['implications']),*public]
    for rule in p['implications']:
        words.extend((*rule['unifies'],len(rule['requires'])))
        for pair in rule['requires']:
            words.extend(pair)
    slots=torch.zeros((2,max(p['ports'])+1),dtype=torch.int32)
    slots[:,p['ports']]=torch.tensor(p['public'],dtype=torch.int32)
    local=[[own[a] for a in p['local_pair']] for own in p['public']]
    return (torch.tensor(words,dtype=torch.int32,device=dev),slots.to(dev),
            torch.tensor(local,dtype=torch.int32,device=dev),p['vertices'])


def schedule(token,inputs,plan,policy,boundaries):
    if policy not in MODES:raise ValueError(policy)
    readers=READERS[boundaries]
    req,port,phase,committed,external,event_ports=(inputs[2],*inputs[4:])
    words,vertices,local,size=plan
    batch,dev=len(req),req.device
    addresses=torch.stack((vertices[req[...,0].long(),port[...,0].long()],
                           vertices[req[...,2].long(),port[...,1].long()]),-1).contiguous()
    picked,pointer,exists=read_parent(token,req)
    all_arrived=torch.ones_like(exists)
    cls=torch.arange(size,device=dev,dtype=torch.int32).repeat(batch,1)
    book=torch.zeros(batch,23,device=dev,dtype=torch.int32)
    empty=torch.full((batch,2),-1,dtype=torch.int32,device=dev)
    published=torch.zeros_like(exists)
    published_rows=torch.full_like(picked,-1)
    published_refs=torch.full_like(addresses,-1)
    stages={}
    arrived=[]
    for tick in range(4):
        if tick==0:
            event=empty
        elif tick<3:
            owner=tick-1
            admitted=(phase[:,owner]>=1)&committed[:,owner].bool()
            event=torch.where(admitted[:,None],local[owner],empty)
        else:
            x=vertices[external[:,1].long(),event_ports[:,0].long()]
            y=vertices[external[:,3].long(),event_ports[:,1].long()]
            event=torch.where(external[:,:1].bool(),torch.stack((x,y),-1),empty)
        observe=tick in readers
        # This list holds only tensors released since the preceding observation.
        # A fused submission has at most three real events in this source schedule.
        event_count=1
        if policy=='fused_fenced':
            arrived.append(event)
            if not observe:
                continue
            event_count=len(arrived)
            event=arrived[0] if event_count==1 else torch.stack(arrived,dim=1)
            arrived.clear()
        flush=(policy=='immediate' or observe) if policy!='late' else tick==3
        flags=int(flush) | (int(observe)<<1) | (int(policy=='no_congruence')<<2) | (int(policy=='stale_negative')<<3)
        snapshot=torch.empty((batch,10),device=dev,dtype=torch.int32)
        kernels().advance(cls,book,event.contiguous(),addresses,words,snapshot,flags,event_count,
                          threads=batch,arg_casts={7:'int32',6:'int32'})
        if observe:
            stage=project(picked,pointer,req,exists & snapshot[:,6:].bool(),all_arrived)
            live=stage['active'].bool()
            delta=live & ~published
            published=published | live
            published_rows=torch.where(delta[...,None],stage['rows'],published_rows)
            published_refs=torch.where(delta[...,None],stage['pointers'].int(),published_refs)
            stages[tick]=dict(classes=snapshot[:,:6],legality=snapshot[:,6:],delta=delta,
                              published=published,published_rows=published_rows,
                              published_refs=published_refs,**stage)
    return stages,book[:,:12]


def run(producer,inputs,table,plan,policy,boundaries):
    first,token=produce(producer,inputs,table)
    stages,counters=schedule(token,inputs,plan,policy,boundaries)
    return first,stages,counters
