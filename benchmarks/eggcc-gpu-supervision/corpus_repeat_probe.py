"""Probe local completion idempotence and repeated GPU emission.

Repeated application of one fixed proven binding is a necessary stopping test,
not ruleset saturation. The oracle-state diagnostic is separate from free rollout.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from corpus_cell_ridge import load_records,features,slot_weights,distances
from boundary_cell_ridge import D,B,state,output_layout,request_with_roles
from dominator_completion import compose,freeze
from collect_observed_corpus import read_bytes
from decode_cell_completion import representation
from bounded_cell_readout import readout_features,decode as decode_bounded
from bake_stop_features import plan as stop_plan,pack as pack_stop,evaluate as stop_features


def wiring(ports,binding,width):
    index={p:i for i,p in enumerate(ports)};indices=np.zeros(width,np.int32);mix=np.zeros((width,B,D),np.float32)
    for i,(slot,symbol) in enumerate(binding):
        indices[i]=index[freeze(symbol)];mix[i]=slot_weights(slot)/np.sqrt(max(1,len(binding)))
    return indices,mix


def attachment(states,indices,mix,xp):
    channels=states[:,D:].reshape(len(states),-1,B)
    picked=xp.take_along_axis(channels,indices[:,:,None],axis=1)
    return xp.sum(xp.matmul(picked[:,:,None,:],mix)[:,:,0,:],axis=1)



def numerical_audit(actual,reference,emissions,reference_emissions):
    finite=np.isfinite(actual)&np.isfinite(reference)
    with np.errstate(invalid='ignore',over='ignore'):
        tolerance=.002+.004*np.abs(reference.astype(np.float64))
        difference=np.abs(actual.astype(np.float64)-reference.astype(np.float64))
    violations=int(np.count_nonzero(~finite|(difference>tolerance)))
    decisions=int(np.count_nonzero(emissions!=reference_emissions))
    return dict(passed=bool(not violations and not decisions),state_elements_outside_tolerance=violations,
                nonfinite_state_elements=int(np.count_nonzero(~finite)),
                emission_disagreements=decisions,max_absolute_state_difference=float(difference[finite].max()) if finite.any() else None,
                absolute_tolerance=.002,relative_tolerance=.004)


def scale_report(scales):
    return [dict(body_max_abs=float(row[0]) if np.isfinite(row[0]) else None,
                 boundary_max_abs=float(row[1]) if np.isfinite(row[1]) else None,
                 boundary_coordinates_outside_teacher_range=int(row[2])) for row in np.asarray(scales)]



def state_bound(source,rule):
    # encode sums at most one tanh vector per fact, divided by sqrt(fact count).
    # In this conditional teacher each effect introduces at most one fact.
    return np.float32(np.sqrt(max(1,len(source)+len(rule['effects']))))


def bound_state(values,body_bound,xp):
    return xp.concatenate([xp.minimum(xp.maximum(values[:,:D],-body_bound[:,None]),body_bound[:,None]),xp.clip(values[:,D:],-1,1)],axis=1)


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);p.add_argument('--rounds',type=int,default=4);p.add_argument('--bounded-state',action='store_true');p.add_argument('--case-output',type=Path);args=p.parse_args()
    if not 1<=args.rounds<=16:raise ValueError('rounds must be between 1 and 16')
    metadata=json.loads(gzip.decompress(args.model.with_suffix('.json.gz').read_bytes()))
    if metadata['manifest_sha256']!=hashlib.sha256(args.manifest.read_bytes()).hexdigest():raise ValueError('model manifest mismatch')
    manifest=json.loads(args.manifest.read_text());records,_=load_records(manifest);records=[r for r in records if r['split']=='test']
    tables={}
    for row in manifest['cases']:
        if row['status']=='complete' and row['split']=='test':
            program=json.loads(read_bytes(Path(row['program'])))
            for table in program['recipe']['tables']:
                previous=tables.setdefault(table['name'],table)
                if previous!=table:raise ValueError('inconsistent table definitions across workloads')
    capacity=metadata['capacity'];family_ids={f:i for i,f in enumerate(metadata['family_names'])};catalog={tuple(v):i for i,v in enumerate(metadata['candidate_keys'])}
    max_inputs=max(1,max(len(r['sample']['binding']) for r in records))
    initial=[];completed=[];queries=[];roles=[];indices=[];mix=[];expected=[];families=[];novels=[];idempotent=[];stop_plans=[]
    for r in records:
        sample=r['sample'];done=sample['completion'];ports,mapping,_=output_layout(sample['source'],done)
        stop_plans.append(stop_plan(sample['source'],r['rule'],sample['binding'],ports,capacity))
        initial.append(state(sample['source'],ports,capacity,allow_absent=True));completed.append(state(done['facts'],ports,capacity,mapping))
        queries.append(request_with_roles(r['rule'],sample['binding'],False));roles.append(request_with_roles(r['rule'],sample['binding'],True) if metadata['positioned_roles'] else np.zeros(D,np.float32))
        idx,weight=wiring(ports,sample['binding'],max_inputs);indices.append(idx);mix.append(weight)
        family=family_ids[r['family']];families.append(family);expected.append(catalog[(family,repr(representation(done['facts'],done['source_map'])),repr(ports))]);novels.append(done['novel'])
        quotient={freeze(a):freeze(b) for a,b in mapping};rebinding=[(slot,quotient[freeze(value)]) for slot,value in sample['binding']]
        repeated,reason=compose(done['facts'],r['rule'],rebinding,tables)
        if reason:raise ValueError('repeat premise missing: '+reason)
        idempotent.append(not repeated['novel'])
    if not all(idempotent):raise ValueError('local completion is not idempotent for every selected input')
    arrays=[np.array(v,np.float32) for v in (initial,completed,queries,roles,mix)]
    initial,completed,q,role,mix=arrays;indices=np.array(indices,np.int32);families=np.array(families,np.int32);novels=np.array(novels,bool)
    with np.load(args.model) as saved:
        w=saved['w'];coef=saved['coef'];prototypes=saved['prototypes'];pf=saved['prototype_families'];stop_coef=saved['stop_coef'] if 'stop_coef' in saved.files else None
        correction=saved['correction_coef'] if 'correction_coef' in saved.files else None
        direct=saved['direct_coef'] if 'direct_coef' in saved.files else None
    direct_mode=metadata.get('direct_mode','tanh')
    if direct_mode not in ('tanh','clip'):raise ValueError('unknown direct readout mode')
    if direct is not None and (stop_coef is None or correction is not None):raise ValueError('direct readout requires stop head and no correction')
    if correction is not None and stop_coef is None:raise ValueError('correction requires Bake stop head')
    body_bounds=np.array([state_bound(r['sample']['source'],r['rule']) for r in records],np.float32)
    if np.any(np.abs(completed[:,:D])>body_bounds[:,None]+1e-5) or np.any(np.abs(completed[:,D:])>1.00001):raise ValueError('teacher violates declared bounds')
    stop_wiring=pack_stop(stop_plans)
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);gw,gc,gidx,gm,gq,gr=[mx.array(v) for v in (w,coef,indices,mix,q,role)]
    if stop_coef is not None:
        gs=mx.array(stop_coef);gstop=[mx.array(v) for v in stop_wiring]
    gbounds=mx.array(body_bounds)
    if direct is not None:gd=mx.array(direct)
    if correction is not None:grc=mx.array(correction)
    def one(s):
        a=attachment(s,gidx,gm,mx);x=features(s,gq,a,gw,mx,gr);out=x@gc
        score=out[:,-1] if stop_coef is None else (mx.concatenate([x,stop_features(s,*gstop,mx)],axis=1)@gs)[:,0]
        emit=score>=.5
        candidate=s+out[:,:-1] if direct is None else decode_bounded(readout_features(s,gq,a,gw,gr,gbounds,gstop,mx)@gd,gbounds,mx,direct_mode)
        if correction is not None:
            ca=attachment(candidate,gidx,gm,mx);cx=features(candidate,gq,ca,gw,mx,gr)
            candidate=candidate+mx.concatenate([cx,stop_features(candidate,*gstop,mx)],axis=1)@grc
        if args.bounded_state:candidate=bound_state(candidate,gbounds,mx)
        return mx.where(emit[:,None],candidate,s),emit
    # Separate oracle diagnostic: the same request on its true completed state.
    oracle,oracle_emit=mx.compile(one)(mx.array(completed));mx.eval(oracle,oracle_emit)
    print(json.dumps(dict(oracle_false_reemissions=int(np.array(oracle_emit).sum()),cases=len(records))),flush=True)
    gp=mx.array(prototypes);gpf=mx.array(pf);gf=mx.array(families)
    def rollout(s):
        emissions=[];state_scales=[]
        for _ in range(args.rounds):
            s,emit=one(s);emissions.append(emit)
            state_scales.append(mx.stack([mx.max(mx.abs(s[:,:D])),mx.max(mx.abs(s[:,D:])),mx.sum((mx.abs(s[:,D:])>1.001).astype(mx.float32))]))
        d=mx.where(gf[:,None]==gpf[None,:],distances(s,gp,mx),mx.inf)
        return s,mx.stack(emissions),mx.argmin(d,axis=1),mx.stack(state_scales)
    final,emissions,selected,state_scales=mx.compile(rollout)(mx.array(initial));mx.eval(final,emissions,selected,state_scales)
    final=np.array(final);emissions=np.array(emissions);selected=np.array(selected)
    reference=initial.copy();reference_emissions=[]
    for _ in range(args.rounds):
        a=attachment(reference,indices,mix,np);x=features(reference,q,a,w,np,role);out=x@coef
        score=out[:,-1] if stop_coef is None else (np.concatenate([x,stop_features(reference,*stop_wiring,np)],axis=1)@stop_coef)[:,0]
        emit=score>=.5
        candidate=reference+out[:,:-1] if direct is None else decode_bounded(readout_features(reference,q,a,w,role,body_bounds,stop_wiring,np)@direct,body_bounds,np,direct_mode)
        if correction is not None:
            ca=attachment(candidate,indices,mix,np);cx=features(candidate,q,ca,w,np,role)
            candidate=candidate+np.concatenate([cx,stop_features(candidate,*stop_wiring,np)],axis=1)@correction
        if args.bounded_state:candidate=bound_state(candidate,body_bounds,np)
        reference=np.where(emit[:,None],candidate,reference);reference_emissions.append(emit)
    numeric=numerical_audit(final,reference,emissions,np.array(reference_emissions))
    if not np.isfinite(final).all() or not np.isfinite(reference).all():
        result=dict(status='failed',reason='nonfinite recurrent state',scope='fixed-binding local GPU recurrence, not ruleset saturation',model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),manifest_sha256=metadata['manifest_sha256'],rounds=args.rounds,cases=len(records),numerical_audit=numeric,state_scales_per_round=scale_report(np.array(state_scales)),emissions_per_round=emissions.sum(1).tolist(),catalog_decode_valid=False,intermediate_cpu_reads=0)
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result,indent=2,allow_nan=False));raise SystemExit(1)
    ambiguous=np.zeros(len(final),bool);invalid_decode=np.zeros(len(final),bool);dp=prototypes.astype(np.float64)
    for start in range(0,len(final),128):
        stop=min(start+128,len(final));d=distances(final[start:stop].astype(np.float64),dp,np);d[families[start:stop,None]!=pf[None,:]]=np.inf
        best=d.min(1);chosen=d[np.arange(stop-start),selected[start:stop]]
        invalid_decode[start:stop]=chosen>best+1e-5
        ambiguous[start:stop]=((d<=best[:,None]+1e-7).sum(1)>1)|(chosen>best+1e-7)
    correct=(selected==np.array(expected))&~ambiguous&~invalid_decode
    stopped=~emissions[-1]
    result=dict(scope='necessary fixed-binding local stop probe, not ruleset saturation',manifest_sha256=metadata['manifest_sha256'],model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),numerical_audit=numeric,decoder_f64_disagreements=int(invalid_decode.sum()),stop_feature_version=metadata.get('stop_feature_version'),rounds=args.rounds,cases=len(records),teacher_idempotent_cases=sum(idempotent),oracle_completed_state_false_reemissions=int(np.array(oracle_emit).sum()),free_rollout=dict(emissions_per_round=emissions.sum(1).tolist(),final_exact_catalog_target=int(correct.sum()),final_ambiguous=int(ambiguous.sum()),stopped_at_final_round=int(stopped.sum()),exact_target_and_stopped=int((correct&stopped).sum()),never_emitted_but_initially_novel=int((~emissions.any(0)&novels).sum()),final_body_rmse=float(np.sqrt(np.mean((final[:,:D]-completed[:,:D])**2)))),intermediate_cpu_reads=0,teacher_state_supplied_between_rounds=False,limitations=['Only repetition of the same fixed binding; not full successor or ruleset closure','Oracle-state test is separate and does not correct the free rollout','Request roles and port wiring are static for the original binding','Catalog includes held-out states and does not prove live identity or visibility','No lifetime, ownership-transfer or global novelty proof'])
    result['state_scales_per_round']=scale_report(np.array(state_scales))
    result['direct_readout']=metadata.get('direct_readout')
    result['bounded_state_ablation']=args.bounded_state
    result['correction']=metadata.get('correction')
    body_mse=np.mean((final[:,:D]-completed[:,:D])**2,axis=1)
    result['failure_diagnostics']=[dict(input_identity=r['identity'],family=r['family'],consumer=r['sample']['consumer'],observations=r['observations'],emissions=emissions[:,i].tolist(),exact_catalog_target=bool(correct[i]),body_rmse=float(np.sqrt(body_mse[i]))) for i,r in enumerate(records) if not stopped[i]]
    if args.case_output:
        case_rows=[dict(identity=r['identity'],family=r['family'],source_facts=len(r['sample']['source']),exact_target=bool(correct[i]),stopped=bool(stopped[i]),initially_novel=bool(novels[i]),emissions=emissions[:,i].tolist(),body_rmse=float(np.sqrt(body_mse[i]))) for i,r in enumerate(records)]
        args.case_output.write_text(json.dumps(dict(model_sha256=result['model_sha256'],manifest_sha256=metadata['manifest_sha256'],rounds=args.rounds,numerical_audit=numeric,cases=case_rows),indent=2)+'\n')
    result['body_error_summary']=dict(median_rmse=float(np.median(np.sqrt(body_mse))),max_rmse=float(np.sqrt(body_mse.max())),active_requests_squared_error_fraction=float(body_mse[~stopped].sum()/max(float(body_mse.sum()),1e-30)))
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not numeric['passed'] or invalid_decode.any():raise SystemExit(1)

if __name__=='__main__':main()
