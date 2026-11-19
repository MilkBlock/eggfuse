"""Online ownership ablation over all Figure 15 observation points."""
from pathlib import Path
import sys
import torch

from arena import Arena
from actor import projected_utility
from train import HERE,produce
sys.path.insert(0,str(HERE.parent/'union_ablation'))
from engine import schedule,device_plan

MODES=('retain','forward','no_retry','blind','unguarded','forward_joint','exact_joint')


def run(actor,producer,x,table,plan,layout,mode,at_tick,collision,audit=False):
    if mode not in MODES or at_tick not in (1,3):raise ValueError((mode,at_tick))
    first,token=produce(producer,x,table)
    scores=projected_utility(token,x[2],actor.pairs,collision) if mode=='exact_joint' else actor(token,x[2],collision)
    arena=Arena(token,layout,mode)
    cursor_log={}
    def read(tick,pointer,exists):
        if tick==at_tick:
            arena.commit(scores,actor.pairs,actor.assignments)
        frames,status=arena.resolve(pointer,torch.ones_like(pointer))
        if audit:
            cursor_log[tick]=status
        return frames[...,50:55].int(),exists & (status>0)
    stages,_=schedule(token,x,plan,'fenced','each',cursor_reader=read)
    if not audit:return stages,arena.targets
    ids=torch.arange(8,device=token.device).expand(len(token),-1)
    old,old_state=arena.resolve(ids,torch.ones_like(ids))
    fresh,fresh_state=arena.resolve(ids,torch.full_like(ids,2))
    _,unknown=arena.resolve(ids,torch.full_like(ids,3))
    return first,stages,dict(token=token,old=old,old_state=old_state,fresh=fresh,fresh_state=fresh_state,
        unknown=unknown,headers=arena.headers,targets=arena.targets,log=arena.log,boundary=arena.boundary,
        physical=arena.source,residual=arena.residual,scores=scores,
        cursors=torch.stack(list(cursor_log.values()),1))
