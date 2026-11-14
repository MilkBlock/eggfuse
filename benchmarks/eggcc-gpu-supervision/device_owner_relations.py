"""Floating shared-owner context using the current exact GPU owner map.

Identity comparisons establish connectivity only. Role vectors are combined by
batched floating products and tanh. This never grants transfer permission.
"""
from device_source_relations import encode


def context(state,sources,valid,coefficients,xp):
    capacity=state['present'].shape[0]
    safe=xp.clip(sources,0,capacity-1)
    in_range=(sources>=0)&(sources<capacity)
    if 'slot_owner' in state:
        owners=state['slot_owner'][safe]
        owner_count=state['owner_live'].shape[0]
        index=xp.clip(owners,0,owner_count-1)
        alive=in_range&(owners>=0)&(owners<owner_count)&state['owner_live'][index]&(state['owner_epoch'][safe]==state['owner_generation'][index])
    else:
        owners=sources
        alive=in_range&state['present'][safe]
    usable=valid&alive
    return encode(owners,coefficients,usable,xp),xp.any(valid&~alive,axis=-1)
