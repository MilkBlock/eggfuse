"""GPU event-driven two-consumer execution of the compiled three-wave fixture.

One receipt slot represents (producer kind, key) in this measured input domain.
Repeated identical facts keep their first publication epoch. A second distinct
value for that same slot violates the experiment's bounded single-value input
contract and sets input_fault on the device. Each consumer keeps its actual RHS
and consumed source identities private until the original finish boundary.
"""
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

import torch


DEFAULT_PLAN = Path(__file__).resolve().parent / 'compiler/plan.json'
MODES = ('barrier', 'local', 'raw', 'guarded', 'guarded_drain', 'barrier_min')
PRODUCERS = ('P0', 'P1', 'U')
KEYS = 4
WAVES = 3
QUOTA = 16
# Parent fields: first wave, value, total identical receipts, invalid input flag.
# Consumer fields: first evaluation, first publish, three projected columns,
# two witnesses x (source kind, key, value, first wave), retirement, first early evaluation.
PARENT_WIDTH, CONSUMER_WIDTH = 4, 15


@lru_cache(maxsize=8)
def _lower_plan(source):
    program=json.loads(source)
    if program.get('schema') != 'eggfuse.readiness-wave/v1' or program.get('schedule') != ['wave0','wave1','wave2','finish']:
        raise ValueError('unsupported source schedule')
    finish=[r for r in program['rules'] if r['ruleset']=='finish']
    if sorted(r['table'] for r in finish) != ['C','V']:
        raise ValueError('expected exactly two emitting finish rules')
    words=[]
    for table,inputs,width in [('C',('P0','P1'),3),('V',('U',),2)]:
        rule=next(r for r in finish if r['table']==table)
        names=rule['inputs'];routes=rule['outputs']
        if sorted(names)!=sorted(inputs) or len(routes)!=width:
            raise ValueError('unsupported relation/projection arity')
        checks=rule['checks']
        if len(inputs)==2:
            if len(checks)!=1 or sorted(checks[0])!=[[0,0],[1,0]]:
                raise ValueError('expected a same-key join between the two parent tables')
        elif checks:
            raise ValueError('unexpected unary condition')
        route_words=[]
        for side,col in routes:
            if type(side) is not int or type(col) is not int or not 0<=side<len(names) or col not in (0,1):
                raise ValueError('unsupported source expression in projected RHS')
            route_words.extend((side,col))
        source_ids=[PRODUCERS.index(n) for n in names]
        words.extend([len(names),*source_ids,*([-1]*(2-len(names))),width,*route_words,*([0]*(6-len(route_words)))])
    return tuple(words)


@dataclass(frozen=True)
class ReadinessPlan:
    words: tuple


def prepare_plan(path=DEFAULT_PLAN):
    """Prepare the compiler plan once before repeated or timed stream construction."""
    return ReadinessPlan(_lower_plan(Path(path).read_bytes()))


_SOURCE = '''
#include <metal_stdlib>
using namespace metal;

// One independent receipt writer per (graph, kind, key). Wave padding has kind 0.
kernel void ingest(device const int* wave, device int* parents, constant int& tick,
                   uint gid [[thread_position_in_grid]]) {
    uint key=gid%4, kind=(gid/4)%3, graph=gid/12;
    device int *p=parents+gid*4;
    for (int e=0;e<16;e++) {
        device const int *event=wave+(graph*16+e)*3;
        if(event[0]==0) continue;
        // Illegal addressing is diagnosed independently of whether it matches
        // this cell, without using a malformed index to perform a device load.
        if(event[0]<1 || event[0]>3 || event[1]<0 || event[1]>=4 || event[2]<0) {
            if(kind==0 && key==0) p[3]=1;
            continue;
        }
        if(event[0]!=int(kind+1) || event[1]!=int(key)) continue;
        if(p[0]<0) { p[0]=tick; p[1]=event[2]; p[2]=1; }
        else if(p[1]==event[2]) { p[2]++; }
        else { p[3]=1; }
    }
}

// A fixed physical slot per (graph, rule, key), independent of its readiness.
// The enclosing branch controls all actual RHS operand reads and writes.
kernel void advance(device const int* parents, device int* consumers,
                    device const uchar* proposals, device const uchar* seal,
                    device int* flags, constant int* plan, constant int& tick,
                    constant int& mode, device uchar* final_flags, device uchar* input_error,
                    uint gid [[thread_position_in_grid]]) {
    uint key=gid%4, rule=(gid/4)%2, graph=gid/8;
    device int *c=consumers+gid*15;
    constant int* cfg=plan+rule*10;
    int arity=cfg[0];
    int first[2]={-1,-1}; bool ready=true; bool closed_gap=false;
    for(int a=0;a<arity;a++) {
        uint slot=(graph*3+uint(cfg[1+a]))*4+key;
        first[a]=parents[slot*4];
        if(first[a]<0) {ready=false; if(tick==3 && seal[slot])closed_gap=true;}
    }
    bool unfinished=c[0]<0;
    bool runnable=ready && unfinished;
    bool proposal=(mode>=2 && proposals[gid]);
    bool drained=mode==4 && tick==3 && runnable && !proposal;
    bool fire=(mode==0 && tick==3 && runnable) || (mode==1 && runnable)
              || (mode==2 && unfinished && proposal) || (mode>=3 && runnable && proposal) || drained;
    int bits=(ready?1:0)|(runnable?2:0)|(proposal?4:0)|(fire?8:0)|(drained?16:0);
    if(fire) {
        int args[2][2]={{-1,-1},{-1,-1}};
        for(int a=0;a<arity;a++) {
            if(first[a]<0) continue;  // raw proposal with an absent parent has a sentinel witness.
            int kind=cfg[1+a]; uint slot=(graph*3+uint(kind))*4+key;
            int v=parents[slot*4+1];
            args[a][0]=int(key);args[a][1]=v;
            int off=5+4*a;
            c[off]=kind+1;c[off+1]=int(key);c[off+2]=v;c[off+3]=first[a];
        }
        for(int col=0;col<cfg[3];col++) c[2+col]=args[cfg[4+2*col]][cfg[5+2*col]];
        c[0]=tick;
        if(!ready) {c[14]=tick;bits|=32;}
    }
    if(tick==3) {
        if(c[0]>=0) {c[1]=tick;bits|=64;}
        else if(closed_gap) c[13]=tick;
        // Write compact live API masks in the actual boundary dispatch. Timed
        // consumers can read these four views without a separate reduction or
        // materializing the per-tick diagnostic snapshots.
        final_flags[gid*4]=c[1]>=0;
        final_flags[gid*4+1]=c[0]<0 && c[13]<0;
        final_flags[gid*4+2]=c[13]>=0;
        final_flags[gid*4+3]=c[14]>=0;
        if(rule==0 && key==0) {
            bool bad=false;
            for(int slot=0;slot<12;slot++) bad=bad || parents[(graph*12+slot)*4+3]>0;
            input_error[graph]=bad;
        }
    }
    flags[gid]=bits;
}
'''


@lru_cache(maxsize=1)
def metal_library():
    return torch.mps.compile_shader(_SOURCE)


class ReadinessEngine:
    """Consume one completed source wave at a time, then open the finish boundary.

    ``proposal_fn(tick, wave)`` receives only this raw observed wave (None on
    finish). It returns an MPS bit tensor [batch, consumer, key]. Host control
    determines only the declared source sequence. No device readiness bit is
    copied to CPU to dispatch a consumer.
    """
    def __init__(self, batch, mode='local', trace=True, device='mps', plan_path=DEFAULT_PLAN, *, plan=None):
        if int(batch)!=batch or batch<1 or mode not in MODES:
            raise ValueError('expected positive batch and a supported schedule')
        self.batch=int(batch);self.device=torch.device(device);self.mode=mode;self.trace=trace
        if self.device.type!='mps' or not torch.backends.mps.is_available():
            raise RuntimeError('the readiness engine requires a Metal GPU')
        if plan is None:plan=prepare_plan(plan_path)
        if not isinstance(plan,ReadinessPlan):raise ValueError('expected a prepared compiler plan')
        self.plan=plan.words
        self.lib=metal_library()
        self.parents=torch.full((self.batch,3,KEYS,PARENT_WIDTH),-1,dtype=torch.int32,device=self.device)
        self.consumers=torch.full((self.batch,2,KEYS,CONSUMER_WIDTH),-1,dtype=torch.int32,device=self.device)
        self.flags=torch.zeros((self.batch,2,KEYS),dtype=torch.int32,device=self.device)
        self.no_proposal=torch.zeros_like(self.flags,dtype=torch.uint8)
        self.unsealed=torch.zeros((self.batch,3,KEYS),dtype=torch.uint8,device=self.device)
        self.final_flags=torch.empty((self.batch,2,KEYS,4),dtype=torch.bool,device=self.device)
        self.input_error=torch.empty((self.batch,),dtype=torch.bool,device=self.device)
        self.tick=0
        self.dispatch_counts=dict(ingest=0,advance=0,diagnostic_advance=0)

    def _bits(self, tensor, shape, name):
        if not torch.is_tensor(tensor) or tensor.device.type!='mps' or tuple(tensor.shape)!=shape:
            raise ValueError(f'{name} must be a device-local tensor with shape {shape}')
        if tensor.dtype not in (torch.bool,torch.uint8,torch.int32,torch.int64):
            raise ValueError(f'{name} must contain discrete bits')
        return tensor.bool().to(torch.uint8).contiguous()

    def _choose(self,wave,proposal_fn,proposal):
        if proposal is not None and proposal_fn is not None:
            raise ValueError('supply a proposal or a proposal function')
        if self.mode in ('barrier','barrier_min','local'):
            if proposal is not None or proposal_fn is not None:
                raise ValueError('exact schedules determine their own admission')
            chosen=self.no_proposal
        else:
            if proposal_fn is not None:proposal=proposal_fn(self.tick,wave)
            if proposal is None:raise ValueError('learned schedule requires proposals')
            chosen=self._bits(proposal,(self.batch,2,KEYS),'proposal')
        return chosen

    def _dispatch_advance(self, chosen, seal, tick, *, diagnostic=False):
        code = 0 if self.mode == 'barrier_min' else MODES.index(self.mode)
        self.lib.advance(self.parents, self.consumers, chosen, seal, self.flags, list(self.plan),
                         tick, code, self.final_flags, self.input_error,
                         threads=self.batch*2*KEYS, arg_casts={5:'int32',6:'int32',7:'int32'})
        self.dispatch_counts['diagnostic_advance' if diagnostic else 'advance'] += 1

    def _advance(self,chosen,seal):
        # This branch uses only the known source schedule. No readiness value
        # is read on the host. Other schedules may perform private work here.
        if not (self.mode == 'barrier_min' and not self.trace and self.tick < WAVES):
            self._dispatch_advance(chosen,seal,self.tick)
        self.tick+=1
        return self.snapshot() if self.trace else None

    def step(self,wave,*,proposal_fn=None,proposal=None):
        if self.tick>=WAVES:raise ValueError('all producer waves were consumed; call finish once')
        if (not torch.is_tensor(wave) or wave.device.type!='mps' or wave.dtype not in (torch.int32,torch.int64)
                or tuple(wave.shape)!=(self.batch,QUOTA,3)):
            raise ValueError(f'expected an MPS integer event tensor [{self.batch},{QUOTA},3]')
        wave=wave.to(torch.int32).contiguous()
        # This wave's source events have just arrived. Validate any external
        # proposal before changing the engine's receipt state so a rejected
        # proposal cannot count the wave twice on retry.
        chosen=self._choose(wave,proposal_fn,proposal)
        self.lib.ingest(wave,self.parents,self.tick,threads=self.batch*3*KEYS,arg_casts={2:'int32'})
        self.dispatch_counts['ingest'] += 1
        return self._advance(chosen,self.unsealed)

    def finish(self,seal,*,proposal_fn=None,proposal=None):
        if self.tick!=WAVES:raise ValueError('finish follows exactly three completed producer waves')
        seal=self._bits(seal,(self.batch,3,KEYS),'seal')
        return self._advance(self._choose(None,proposal_fn,proposal),seal)

    def snapshot(self):
        """Snapshot actual receipts, private execution, provenance and public visibility on device."""
        if self.mode=='barrier_min' and not self.trace and 0 < self.tick <= WAVES:
            # Optional diagnostics explicitly request the omitted readiness
            # observation. At every such source tick the barrier forbids firing.
            self._dispatch_advance(self.no_proposal,self.unsealed,self.tick-1,diagnostic=True)
        p=self.parents.clone();c=self.consumers.clone();f=self.flags.clone()
        def bit(mask):return f.bitwise_and(mask)!=0
        computed=c[...,0]>=0;public=c[...,1]>=0;retired=c[...,13]>=0;pending=~(computed|retired)
        rows=c[...,2:5];ready=bit(1)
        return dict(tick=self.tick-1,parent_live=p[...,0]>=0,parent_value=p[...,1],
            parent_first_tick=p[...,0],parent_version=p[...,0]+1,receipt_count=p[...,2].clamp_min(0),
            input_fault=(p[...,3]>0).flatten(1).any(1),ready=ready,runnable=bit(2),proposal=bit(4),fired=bit(8),
            drained=bit(16),early=bit(32),published=bit(64),computed=computed,hidden=computed&~public,
            public=public,pending=pending,sealed_absent=retired,pending_open=pending&~ready,
            withheld=pending&ready,first_fired_tick=c[...,0],first_publish_tick=c[...,1],
            first_early_tick=c[...,14],rows=rows,public_rows=torch.where(public[...,None],rows,-1),
            witness=c[...,5:13].reshape(self.batch,2,KEYS,2,4))

    def endpoint(self):
        """Return final GPU buffer views. Consumers must treat these views as read-only.

        The finish dispatch opens every computed RHS at the same boundary, so
        each unpublished row/witness slot still contains its initial sentinel.
        An input outside the single-value fixture contract is marked input_fault.
        """
        if self.tick != WAVES + 1:
            raise ValueError('public endpoint requires the completed finish boundary')
        state = self.consumers
        return dict(public=self.final_flags[...,0], public_rows=state[...,2:5],
                    witness=state[...,5:13].view(self.batch,2,KEYS,2,4),
                    pending=self.final_flags[...,1], sealed_absent=self.final_flags[...,2],
                    early_execution=self.final_flags[...,3], input_fault=self.input_error,
                    first_fired_tick=state[...,0], first_publish_tick=state[...,1])

    def result(self):
        if self.tick!=WAVES+1:raise ValueError('final result requested before finish')
        return self.snapshot()


def run_engine(events,seal,mode='local',*,trace=True,proposal_fn=None,proposals=None,plan_path=DEFAULT_PLAN,plan=None):
    """Convenience wrapper. Online clients may stream arrivals separately via step()."""
    if events.ndim!=4 or events.shape[1]!=WAVES:raise ValueError('expected [batch,3,16,3]')
    engine=ReadinessEngine(len(events),mode,trace,events.device,plan_path,plan=plan)
    snapshots=[]
    for t in range(WAVES+1):
        kw=dict(proposal_fn=proposal_fn,proposal=None if proposals is None else proposals[:,t])
        frame=engine.step(events[:,t],**kw) if t<WAVES else engine.finish(seal,**kw)
        if trace:snapshots.append(frame)
    final=snapshots[-1] if trace else engine.result()
    traces={k:torch.stack([frame[k] for frame in snapshots],1) for k in final if k!='tick'} if trace else None
    return final,traces
