"""Known-family, whole-workload ridge experiment over the observed eggcc corpus.

One GPU row predicts a whole Cell body and boundary state. Initial encodings are
prepared once on CPU; this experiment does not discover live matches or iterate
to saturation. Candidate decoding uses a known Bake catalog including heldouts.
"""
import argparse
from functools import lru_cache
import hashlib
import gzip
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes,digest
from profile_observed_corpus import template_key,key
from boundary_cell_ridge import D,B,state,output_layout,request_with_roles
from whole_cell_ridge import code,train
from dominator_completion import freeze,compose
from decode_cell_completion import representation


@lru_cache(maxsize=512)
def slot_weights(slot):
    return np.array([code(('boundary-request',slot,j)) for j in range(B)],np.float32)


def initial_attachment(values,ports,binding):
    index={p:i for i,p in enumerate(ports)};channels=values[D:].reshape(-1,B)
    result=np.zeros(D,np.float32)
    for slot,symbol in binding:result+=channels[index[freeze(symbol)]]@slot_weights(slot)
    return result/np.sqrt(max(1,len(binding)))


def features(s,q,a,w,xp,roles=None):
    h=s[:,:D];attached=xp.tanh(a);q=xp.tanh(q+attached)
    x=xp.concatenate([h,q,h*q,xp.abs(h-q),attached],axis=1)
    if roles is not None:x=xp.concatenate([x,roles],axis=1)
    return xp.concatenate([xp.ones((len(s),1),dtype=xp.float32),x,xp.tanh(x@w)],axis=1)


def load_records(manifest):
    records={};failures=[]
    for entry in manifest['cases']:
        if entry['status']!='complete':failures.append(entry['case']);continue
        if digest(Path(entry['targets']))!=entry['targets_sha256']:raise ValueError('target fingerprint mismatch')
        program=json.loads(read_bytes(Path(entry['program'])));data=json.loads(read_bytes(Path(entry['targets'])))
        if program['sha256']!=data['program_sha256']:raise ValueError('program mismatch')
        tables={t['name']:t for t in program['recipe']['tables']}
        for sample in data['targets']:
            rule=program['recipe']['rules'][sample['consumer']];family=template_key(rule)
            identity=key((family,sample['source'],sample['binding']));group=(entry['split'],identity)
            if group in records:
                if records[group]['sample']['completion']!=sample['completion']:raise ValueError('same input has conflicting conditional targets')
                records[group]['observations']+=sample['observations'];continue
            records[group]=dict(split=entry['split'],identity=identity,family=family,rule=rule,tables=tables,sample=sample,observations=sample['observations'])
        print(json.dumps(dict(loaded=entry['case'],unique_partition_inputs=len(records))),flush=True)
    return list(records.values()),failures


def distances(values,prototypes,xp):
    # Both groups receive equal aggregate weight; global padding is explicit.
    h=values[:,:D];p=prototypes[:,:D];b=values[:,D:];c=prototypes[:,D:]
    body=(xp.sum(h*h,axis=1)[:,None]+xp.sum(p*p,axis=1)[None,:]-2*h@p.T)/D
    boundary=(xp.sum(b*b,axis=1)[:,None]+xp.sum(c*c,axis=1)[None,:]-2*b@c.T)/max(1,b.shape[1])
    return body+boundary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('manifest',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--no-positioned-roles',action='store_true');parser.add_argument('--model-output',type=Path);parser.add_argument('--completion-controls',action='store_true');args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text());records,failures=load_records(manifest)
    layouts=[output_layout(r['sample']['source'],r['sample']['completion']) for r in records]
    capacity=max(len(p) for p,_,_ in layouts);families={f:i for i,f in enumerate(sorted({r['family'] for r in records}))}
    states=[];queries=[];role_columns=[];attachments=[];targets=[];novels=[];splits=[];row_families=[];identities=[];weights=[];expected=[]
    dictionary={};prototypes=[];prototype_families=[]
    def candidate(family,facts,mapping,ports,vector):
        signature=(family,repr(representation(facts,mapping)),repr(ports))
        if signature not in dictionary:
            dictionary[signature]=len(prototypes);prototypes.append(vector);prototype_families.append(family)
        return dictionary[signature]
    for i,(r,(ports,mapping,_)) in enumerate(zip(records,layouts)):
        sample=r['sample'];completion=sample['completion'];family=families[r['family']]
        initial=state(sample['source'],ports,capacity,allow_absent=True)
        target=state(completion['facts'],ports,capacity,mapping)
        q=request_with_roles(r['rule'],sample['binding'],False)
        role=request_with_roles(r['rule'],sample['binding'],True) if not args.no_positioned_roles else np.zeros(D,np.float32)
        attachment=initial_attachment(initial,ports,sample['binding'])
        original=sorted({freeze(v) for _,xs,*_ in sample['source'] for v in xs},key=repr)
        expected.extend([candidate(family,completion['facts'],completion['source_map'],ports,target),candidate(family,sample['source'],[(p,p) for p in original],ports,initial)])
        role_columns.extend([role,np.zeros(D,np.float32)]);states.extend([initial,initial]);targets.extend([target,initial]);queries.extend([q,np.zeros(D,np.float32)]);attachments.extend([attachment,np.zeros(D,np.float32)])
        novels.extend([completion['novel'],False]);splits.extend([r['split']]*2);row_families.extend([family]*2);identities.extend([r['identity']]*2);weights.extend([r['observations'],0])
        if i%250==0:print(json.dumps(dict(encoded=i,total=len(records))),flush=True)
    base_rows=len(states)
    if args.completion_controls:
        # Same legitimate request on its already-completed state, not the
        # unrelated zero-request identity control. Preserve workload partitions.
        for i,(record,(ports,_,_)) in enumerate(zip(records,layouts)):
            source_index=2*i;completed=targets[source_index]
            sample=record['sample'];mapping={freeze(a):freeze(b) for a,b in sample['completion']['source_map']}
            repeated,reason=compose(sample['completion']['facts'],record['rule'],[(slot,mapping[freeze(v)]) for slot,v in sample['binding']],record['tables'])
            if reason or repeated['novel']:raise ValueError('unproved completed-state negative example')
            states.append(completed);targets.append(completed);queries.append(queries[source_index]);role_columns.append(role_columns[source_index])
            attachments.append(initial_attachment(completed,ports,record['sample']['binding']))
            novels.append(False);splits.append(record['split']);row_families.append(row_families[source_index]);identities.append(record['identity']+':completed');weights.append(0);expected.append(expected[source_index])
    role_columns=np.array(role_columns,np.float32);s=np.array(states,np.float32);q=np.array(queries,np.float32);a=np.array(attachments,np.float32);target=np.array(targets,np.float32);novel=np.array(novels,bool)
    split=np.array(splits);rf=np.array(row_families,np.int32);weights=np.array(weights);expected=np.array(expected);real=(np.arange(len(s))<base_rows)&(np.arange(len(s))%2==0);completion_control=np.arange(len(s))>=base_rows
    prototypes=np.array(prototypes,np.float32);pf=np.array(prototype_families,np.int32)
    train_mask=split=='train';val=split=='validation'
    w=np.random.default_rng(119).normal(0,1/16,(6*D,512)).astype(np.float32)
    x=features(s,q,a,w,np,role_columns);y=np.column_stack([target-s,novel.astype(np.float32)])
    loss_scale=np.concatenate([np.full(D,1/np.sqrt(D)),np.full(s.shape[1]-D,1/np.sqrt(s.shape[1]-D)),[1]]).astype(np.float32)
    coef,fit=train(x,y*loss_scale,train_mask,val);coef/=loss_scale[None,:]
    if not mx.metal.is_available():raise RuntimeError('Metal unavailable')
    mx.set_default_device(mx.gpu);gw=mx.array(w);gc=mx.array(coef);gp=mx.array(prototypes);gf=mx.array(pf)
    def inference(s,q,a,families,roles):
        out=features(s,q,a,gw,mx,roles)@gc;emit=out[:,-1]>=.5
        predicted=mx.where(emit[:,None],s+out[:,:-1],s)
        distance=mx.where(families[:,None]==gf[None,:],distances(predicted,gp,mx),mx.inf)
        return predicted,emit,mx.argmin(distance,axis=1)
    predicted,emit,chosen=mx.compile(inference)(mx.array(s),mx.array(q),mx.array(a),mx.array(rf),mx.array(role_columns));mx.eval(predicted,emit,chosen)
    predicted=np.array(predicted);emit=np.array(emit);chosen=np.array(chosen)
    raw=x@coef;cpu_emit=raw[:,-1]>=.5;cpu_state=np.where(cpu_emit[:,None],s+raw[:,:-1],s)
    np.testing.assert_allclose(predicted,cpu_state,rtol=2e-3,atol=1e-3);np.testing.assert_array_equal(emit,cpu_emit)
    # Independent f64 selection check in bounded chunks, including near ties.
    ambiguous=np.zeros(len(s),bool);dp=prototypes.astype(np.float64)
    for start in range(0,len(s),128):
        stop=min(start+128,len(s));d=distances(predicted[start:stop].astype(np.float64),dp,np)
        d[rf[start:stop,None]!=pf[None,:]]=np.inf;best=d.min(1)
        selected=d[np.arange(stop-start),chosen[start:stop]]
        if np.any(selected>best+1e-5):raise ValueError('GPU decode disagrees with f64 audit')
        ambiguous[start:stop]=((d<=best[:,None]+1e-7).sum(1)>1)|(selected>best+1e-7)
    training_inputs={identities[i] for i in np.flatnonzero(train_mask)};training_families=set(rf[train_mask])
    seen=np.array([v in training_inputs for v in identities]);known=np.array([v in training_families for v in rf])
    correct=(chosen==expected)&~ambiguous
    reports={}
    masks=[(part,split==part) for part in ['train','validation','test']]+[('test_seen_input',(split=='test')&seen),('test_new_input_known_family',(split=='test')&~seen&known),('test_uncovered_family',(split=='test')&~known)]
    for name,mask in masks:
        actual=mask&real;positive=actual&novel
        reports[name]=dict(unique_inputs=int(actual.sum()),represented_observations=int(weights[actual].sum()),locally_novel=int(positive.sum()),novel_exact_and_emitted=int((positive&correct&emit).sum()),novel_wrong_emitted=int((positive&~correct&emit&~ambiguous).sum()),novel_ambiguous_emitted=int((positive&emit&ambiguous).sum()),novel_not_emitted=int((positive&~emit).sum()),no_op_false_emissions=int((actual&~novel&emit).sum()),identity_control_false_emissions=int((mask&~real&~completion_control&emit).sum()),completion_control_false_emissions=int((mask&completion_control&emit).sum()),exact_final_state=int((actual&correct).sum()),exact_state_and_emission_decision=int((actual&correct&(emit==novel)).sum()),body_rmse=float(np.sqrt(np.mean((predicted[actual,:D]-target[actual,:D])**2))) if actual.any() else None)
    result=dict(scope='standalone corpus GPU whole-Cell proposal and known-catalog decoding; not a full runtime',manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),completion_controls=args.completion_controls,backpropagation=False,positioned_roles=not args.no_positioned_roles,role_integration='additional columns; original request retained',fit=fit,training='one row per unique partition input plus identity controls and optional completed-state controls; validation-only regularizer selection, balanced body/boundary/emission loss',state_floats=s.shape[1],unique_partition_inputs=len(records),candidate_states=len(prototypes),families=len(families),excluded_workloads=failures,reports=reports,limitations=['CPU successful matches still supply initial states','Candidate catalog includes held-out symbolic states and is scoped by compiler family','Exact target is recorded body, quotient map and layout, not semantic alpha-equivalence','Reported first-step inference does not test successor closure, off-manifold recovery or stopping','No speedup, live constructor identity, Run visibility or ownership retirement proof','Uncovered-family predictions are diagnostic and require CPU fallback','Scalar values are encoded, not generally computed by this model'])
    if args.model_output:
        args.model_output.parent.mkdir(parents=True,exist_ok=True)
        with args.model_output.open('wb') as output:
            np.savez_compressed(output,w=w,coef=coef,prototypes=prototypes,prototype_families=pf)
        metadata=dict(schema='corpus-cell-ridge/v1',manifest_sha256=result['manifest_sha256'],body_width=D,boundary_width=B,capacity=capacity,positioned_roles=result['positioned_roles'],completion_controls=args.completion_controls,family_names=sorted(families),candidate_keys=[signature for signature,index in sorted(dictionary.items(),key=lambda item:item[1])],limitations=result['limitations'])
        metadata_path=args.model_output.with_suffix('.json.gz');metadata_path.write_bytes(gzip.compress(json.dumps(metadata).encode(),mtime=0))
        result['model_artifact']=dict(weights=str(args.model_output),weights_sha256=hashlib.sha256(args.model_output.read_bytes()).hexdigest(),metadata=str(metadata_path),metadata_sha256=hashlib.sha256(metadata_path.read_bytes()).hexdigest())
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
