"""GPU two-block semantic ownership handoff over certified physical transfer.

This initial path joins two singleton owners. Further joins fail explicitly until
Bake/model supply a larger block layout; they never discard an inherited block.
Logical Entries retain original port roles and select a block in the new owner.
"""
from device_slot_owners import transfer
from neural_semantic_owner import initialize as initialize_directory


def initialize(state,xp):
    if 'token_source' in state:raise ValueError('initialize block directory before semantic transfers')
    out=initialize_directory(state,xp)
    out['owner_token_blocks']=xp.stack([state['tokens'],xp.zeros_like(state['tokens'])],axis=1)
    out.pop('tokens')
    out['token_block']=xp.zeros(len(state['present']),xp.int32)
    out['owner_block_count']=state['present'].astype(xp.int32)
    return out


def handoff(state,plan,source,target,source_generation,target_generation,logit,blocks,certified,quiescent,xp):
    if blocks.shape!=(2,128):raise ValueError('two complete token blocks required')
    n=len(state['present']);s=xp.clip(source,0,n-1);t=xp.clip(target,0,n-1)
    refs=state['token_source'];epochs=state['token_source_generation']
    singleton=(state['owner_block_count'][s]==1)&(state['owner_block_count'][t]==1)&(refs[s]==s)&(refs[t]==t)
    aliases=((refs==s)|(refs==t))&state['present']
    valid=xp.all(~aliases|((state['token_block']==0)&(epochs==xp.where(refs==s,source_generation,target_generation))))
    enabled=certified&singleton&valid&xp.all(xp.isfinite(blocks))&xp.isfinite(logit)&(logit>=0)
    out,marks=transfer(state,plan,source,target,source_generation,target_generation,enabled&quiescent,xp)
    ok=marks['transferred'];source_alias=(refs==s)&state['present']&ok;target_alias=(refs==t)&state['present']&ok
    out['token_source']=xp.where(source_alias,t,refs)
    out['token_source_generation']=xp.where(source_alias,target_generation,epochs)
    out['token_block']=xp.where(source_alias,0,xp.where(target_alias,1,state['token_block']))
    row=xp.arange(n)
    out['owner_token_blocks']=xp.where(((row==t)&ok)[:,None,None],blocks[None,:,:],state['owner_token_blocks'])
    out['owner_block_count']=xp.where((row==t)&ok,2,xp.where((row==s)&ok,0,state['owner_block_count']))
    return out,dict(marks,semantic_blocks_adopted=ok,block_capacity_boundary=~singleton,stale_block_alias=~valid)
