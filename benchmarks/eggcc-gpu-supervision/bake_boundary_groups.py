"""Host-side grouping of identical boundary encoders, excluding query ports."""
import numpy as np


def group_boundary_plans(blocks):
    groups={};out=[]
    for stage,plan in blocks:
        if 'boundary_context' not in plan:out.append((stage,plan));continue
        parts=[]
        for key,value in sorted(plan['boundary_context'].items()):
            if key in ('ports','port_sorts'):continue
            if not isinstance(value,(np.ndarray,bool,int,float,np.generic)):raise ValueError('group before device upload')
            a=np.asarray(value)
            parts.append((key,a.dtype.str,a.shape,a.tobytes()))
        identity=(bool(plan.get('shared_boundary_context',False)),tuple(parts))
        group=groups.setdefault(identity,len(groups))
        out.append((stage,dict(plan,boundary_group=group)))
    return out
