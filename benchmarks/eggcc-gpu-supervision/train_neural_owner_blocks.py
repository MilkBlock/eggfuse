"""Synthetic two-block ownership learning; full joint Eq audit on MLX GPU."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from mlx.utils import tree_flatten
from neural_cell_samples import samples
from neural_cell_chains import chains
from neural_cell_transition import loss as direct_loss
from neural_owner_blocks import OwnerBlocks,replay,joint_arrays
from neural_eq_readout import masked_loss,metrics
from train_neural_cell_chains import fingerprints


def build(recipe,count,seed):
    records=[];base=samples(recipe,count,seed,records,ordered=True)
    data,coverage=chains(recipe,records,ordered=True,eq_targets=True,block_owner=True)
    return base,data,coverage


def objective(model,batch,parent,chain):
    _,_,blocks=replay(model,parent,chain)
    source,target,cross=model.readout(blocks,chain['source_request'],chain['request'],chain['owner_request'])
    align=mx.mean((blocks[:,0]-chain['source_target'])**2+(blocks[:,1]-chain['target'])**2,axis=1)
    return (direct_loss(model.cell,batch)+mx.sum(align*chain['valid'])/mx.maximum(mx.sum(chain['valid']),1)
        +masked_loss(source,chain['source_eq_target'],chain['source_eq_mask'])
        +masked_loss(target,chain['eq_target'],chain['eq_mask'])
        +masked_loss(cross,chain['cross_eq_target'],chain['cross_eq_mask']))


def signatures(base,data):
    return [hashlib.sha256(sig.encode()+a.tobytes()+b.tobytes()).hexdigest()
            for sig,a,b in zip(fingerprints(base,data),data['owner_request'],data['source_request'])]


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('transition',type=Path);p.add_argument('eq',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--steps',type=int,default=1200);a=p.parse_args()
    if a.steps<1:raise ValueError('positive training steps')
    source=json.loads(a.trace.read_text());source=source.get('recipe',source)
    recipe=dict(source,rules=[r for r in source['rules'] if r['metadata']['source_set']=='context'])
    began=time.perf_counter();base,chain,coverage=build(recipe,8,23001);test,tc,test_coverage=build(recipe,4,93003)
    width=max(len(r['slots']) for r in recipe['rules'])
    seen=set(signatures(base,chain));overlap=np.array([sig in seen for sig in signatures(test,tc)])
    device=lambda d:{k:mx.array(v) for k,v in d.items()}
    db,dc=map(device,(base,chain));mx.random.seed(117)
    model=OwnerBlocks(base['x'].shape[-1],base['relations'].shape[-1],width)
    model.cell.load_weights(str(a.transition));model.eq.load_weights(str(a.eq))
    frozen={k:np.array(v) for k,v in tree_flatten(model.cell.parameters()) if k.startswith(('relation.','match_relation.'))}
    def evaluate(b,c):
        all_scores=[];old_scores=[];accept=[];mse=[]
        for start in range(0,len(c['valid']),128):
            cc=device({k:v[start:start+128] for k,v in c.items()});pp=device({k:v[c['parent'][start:start+128]] for k,v in b.items()})
            first,second,blocks=replay(model,pp,cc)
            scores=model.readout(blocks,cc['source_request'],cc['request'],cc['owner_request'])
            _,old=model.cell(pp['x'],pp['edges'],pp['mask'],pp['request'],pp['relations'])
            old_eq=model.eq(old,cc['source_request']);mx.eval(scores,first,second,blocks,old_eq)
            all_scores.append(tuple(np.array(v) for v in scores));old_scores.append(np.array(old_eq));accept.append((np.array(first)>=0)&(np.array(second)>=0))
            mse.append(np.mean((np.array(blocks[:,0])-c['source_target'][start:start+128])**2+(np.array(blocks[:,1])-c['target'][start:start+128])**2,axis=1))
        scores=[np.concatenate([s[i] for s in all_scores]) for i in range(3)]
        labels=[c[k] for k in ('source_eq_target','eq_target','cross_eq_target')];masks=[c[k] for k in ('source_eq_mask','eq_mask','cross_eq_mask')]
        joint=joint_arrays(*scores,width);truth=joint_arrays(*labels,width);mask=joint_arrays(*masks,width)
        pos=c['valid'];changed=pos&np.any((c['source_eq_before']!=c['source_eq_target'])&c['source_eq_mask'],axis=1)
        report=dict(matching_errors=int((np.concatenate(accept)!=pos).sum()),two_block_mse=float(np.concatenate(mse)[pos].mean()),
            combined=metrics(joint[pos],truth[pos],mask[pos],2*width),
            source_entry=metrics(scores[0][pos],labels[0][pos],masks[0][pos],width),
            target_entry=metrics(scores[1][pos],labels[1][pos],masks[1][pos],width),
            changed_source_states=int(changed.sum()),source_after_update_on_changed=metrics(scores[0][changed],labels[0][changed],masks[0][changed],width),
            source_without_update_on_changed=metrics(np.concatenate(old_scores)[changed],labels[0][changed],masks[0][changed],width),
            cross_wrong_states=int((((scores[2]>=0)!=(labels[2]>0))&masks[2]&pos[:,None]).any(axis=1).sum()))
        return report,(joint,truth,mask)
    before,_=evaluate(test,tc);print(json.dumps(dict(before=before,coverage=coverage)),flush=True)
    grad=nn.value_and_grad(model,objective);opt=optim.Adam(learning_rate=5e-4);rng=np.random.default_rng(119)
    for step in range(a.steps):
        ci=mx.array(rng.integers(len(chain['valid']),size=64));bi=mx.array(rng.integers(len(base['valid']),size=128))
        c={k:v[ci] for k,v in dc.items()};parent={k:v[c['parent']] for k,v in db.items()};batch={k:v[bi] for k,v in db.items()}
        value,g=grad(model,batch,parent,c);opt.update(model,g);mx.eval(value,model.parameters(),opt.state)
        if step%100==0:print(json.dumps(dict(step=step,loss=float(value))),flush=True)
    after,arrays=evaluate(test,tc);training,_=evaluate(base,chain);novel=tc['valid']&~overlap
    after['unseen']=metrics(*(v[novel] for v in arrays),2*width)
    current=dict(tree_flatten(model.cell.parameters()));unchanged=all(np.array_equal(v,np.array(current[k])) for k,v in frozen.items())
    if not unchanged:raise AssertionError('matching weights changed')
    model.save_weights(str(a.output.with_suffix('.safetensors')))
    report=dict(scope='standalone GPU two-block semantic-owner learning; no runtime commits or saturation',synthetic_only_training=True,backpropagation=True,slot_width=width,token_blocks=2,floats_per_owner=256,train=coverage,test=test_coverage,test_input_overlap=int(overlap.sum()),before=before,after=after,training=training,steps=a.steps,interface_head_unchanged=unchanged,wall_seconds=time.perf_counter()-began,parent_transition_sha256=hashlib.sha256(a.transition.read_bytes()).hexdigest(),parent_eq_sha256=hashlib.sha256(a.eq.read_bytes()).hexdigest(),weights_sha256=hashlib.sha256(a.output.with_suffix('.safetensors').read_bytes()).hexdigest(),promoted_for_execution=False,limitations=['Fixed two-step routing; blocks are not yet consumed by runtime third steps','Two-block cost doubles resident floats versus a single token','No stable identity or incidence is supplied to the Eq readouts','No CPU audit rollback or full-stage scheduling integration'])
    report['semantic_status']='pass' if after['combined']['closed_exact_states']==after['combined']['states'] and after['matching_errors']==0 else 'difference'
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(after),flush=True)


if __name__=='__main__':main()
