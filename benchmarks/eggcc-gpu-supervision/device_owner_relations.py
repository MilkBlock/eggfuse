"""Floating shared-owner context using the current exact GPU owner map.

Identity comparisons establish connectivity only. Role vectors are combined by
batched floating products and tanh. This never grants transfer permission.
"""
from device_source_relations import encode


def snapshot(state,sources,valid,xp):
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
    return dict(owners=owners,usable=valid&alive,missing=xp.any(valid&~alive,axis=-1),
        owner_epoch=state['owner_epoch'][safe] if 'slot_owner' in state else state['generation'][safe],
        physical_generation=state['owner_generation'][index] if 'slot_owner' in state else state['generation'][safe],
        physical_live=state['owner_live'][index] if 'slot_owner' in state else state['present'][safe])


def context(state,sources,valid,coefficients,xp):
    saved=snapshot(state,sources,valid,xp)
    return encode(saved['owners'],coefficients,saved['usable'],xp),saved['missing']
