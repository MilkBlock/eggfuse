"""Exact shared coefficient layouts, separate from dynamic source bindings.

Grouping identical numeric layouts is not proof of Cell equivalence or ownership.
In the audit driver, observed edges supply layouts; a runtime compiler must derive
these from legal Entry wiring and provider multiplicities.
"""
import numpy as np


def group_layouts(nodes,channels,width=128):
    groups={}
    for index,node in enumerate(nodes):
        count=len(node['edges'])
        edge=np.zeros((1,max(count,1),width),np.float32)
        route=np.zeros((1,max(count,1),channels),np.float32)
        for j,(_,value) in enumerate(node['edges']):
            edge[0,j]=value;route[0,j]=node['edge_routes'][j]
        # Exact signatures include multiplicity and ordered ports, not source IDs.
        key=(count,edge.tobytes(),route.tobytes())
        if key not in groups:groups[key]=dict(edge=edge,route=route,indices=[],count=count)
        groups[key]['indices'].append(index)
    return list(groups.values())


def pack_audit_requests(nodes,indices,seed,q,layout):
    """Saved-state audit only: generation 1 and complete source snapshot supplied."""
    n=len(indices);e=layout['edge'].shape[1];count=layout['count']
    sources=np.zeros((n,e),np.int32)
    for row,i in enumerate(indices):
        if len(nodes[i]['edges'])!=count:raise ValueError('source arity differs from shared layout')
        sources[row,:count]=[src for src,_ in nodes[i]['edges']]
    return dict(seed=seed[indices],q=q[indices],sources=sources,
                generations=np.ones((n,e),np.int32),edge_valid=np.broadcast_to(np.arange(e)<count,(n,e)).copy(),
                input_ready=np.ones(n,bool))
