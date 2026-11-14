"""Two token blocks under one semantic owner, with learned source-state update.

No runtime identities enter the readouts. Static block projections retain their
original port numbering; CPU reference data is used only for supervision.
"""
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from neural_eq_readout import EqReadout,targets
from neural_ordered_relations import ordered_model
from train_neural_cell_chains import incoming_tokens


def supervision(recipe,plan,source_values,target_values,before,after,width):
    from neural_combined_cell import compose,request
    from neural_cell_chains import code
    from multi_entry_ridge import template
    source,target=[recipe['rules'][plan[k]] for k in ('producer','consumer')]
    old=targets(source,source_values,before,width);new=targets(source,source_values,after,width)
    cross=np.zeros((width,width),np.float32);mask=np.zeros_like(cross,bool)
    for i,sv in enumerate(source_values):
        for j,tv in enumerate(target_values):
            a,b=source['slots'][i]['sort'],target['slots'][j]['sort']
            if a['kind']=='eq' and a==b:
                mask[i,j]=True;cross[i,j]=after.root(sv)==after.root(tv)
    return dict(source_request=template(source)[1],owner_request=request(compose(recipe,plan)),
        source_target=code(source,[after.root(v) for v in source_values],after),
        source_eq_target=new['eq_target'],source_eq_before=old['eq_target'],source_eq_mask=new['eq_mask'],
        cross_eq_target=cross.reshape(-1),cross_eq_mask=mask.reshape(-1))


class OwnerBlocks(nn.Module):
    def __init__(self,input_width,relation_width,width):
        super().__init__();self.width=width
        self.cell=ordered_model(input_width,relation_width,True)
        self.cell.relation.freeze();self.cell.match_relation.freeze()
        self.eq=EqReadout(width)
        self.update_source=nn.Sequential(nn.Linear(448,128),nn.GELU(),nn.Linear(128,128))
        self.update_source.layers[-1].weight=mx.zeros_like(self.update_source.layers[-1].weight)
        self.update_source.layers[-1].bias=mx.zeros_like(self.update_source.layers[-1].bias)
        self.cross=nn.Sequential(nn.Linear(448,128),nn.GELU(),nn.Linear(128,128),nn.GELU(),nn.Linear(128,width*width))

    def advance(self,source,inputs,edges,mask,source_request,target_request,owner_request,relations):
        accepted,target=self.cell.transition(inputs,edges,mask,target_request,relations)
        features=mx.concatenate([source,target,source_request,target_request,owner_request],axis=-1)
        updated=source+self.update_source(features)
        return accepted,mx.stack([updated,target],axis=1)

    def readout(self,blocks,source_request,target_request,owner_request):
        a=self.eq(blocks[:,0],source_request);b=self.eq(blocks[:,1],target_request)
        features=mx.concatenate([blocks[:,0],blocks[:,1],source_request,target_request,owner_request],axis=-1)
        return a,b,self.cross(features)


def replay(model,parent,chain):
    first,source=model.cell(parent['x'],parent['edges'],parent['mask'],parent['request'],parent['relations'])
    incoming=incoming_tokens(model.cell,chain,source)
    second,blocks=model.advance(source,incoming,chain['edges'],chain['mask'],chain['source_request'],chain['request'],chain['owner_request'],chain['relations'])
    return first,second,blocks


def joint_arrays(source,target,cross,width):
    """Assemble the full Eq graph for audit, including cross-block consequences."""
    a,b=np.triu_indices(2*width,1);si,sj=np.triu_indices(width,1)
    index={(int(i),int(j)):k for k,(i,j) in enumerate(zip(si,sj))}
    out=np.empty((len(source),len(a)),source.dtype)
    for k,(i,j) in enumerate(zip(a,b)):
        if j<width:out[:,k]=source[:,index[int(i),int(j)]]
        elif i>=width:out[:,k]=target[:,index[int(i-width),int(j-width)]]
        else:out[:,k]=cross[:,i*width+j-width]
    return out
