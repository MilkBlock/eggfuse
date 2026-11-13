"""Ridge Cell completion recurrent entirely in a shared latent state."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from corpus_cell_ridge import load_records,slot_weights,distances
from boundary_cell_ridge import D,B,state,output_layout,request_with_roles
from corpus_repeat_probe import state_bound,numerical_audit
from bounded_cell_readout import normalize
from dominator_completion import freeze,compose
from decode_cell_completion import representation
from whole_cell_ridge import train


def encode_state(values,bounds,gains,basis,scale):
    weighted=normalize(values,bounds,np)*scale;weighted[:,D:]*=gains[:,None]
    return weighted@basis


def decode_state(z,bounds,gains,basis,scale,xp):
    unit=(z@basis.T)/scale
    return xp.concatenate([unit[:,:D]*bounds[:,None],unit[:,D:]/gains[:,None]],axis=1)


def compile_attachment(ports,binding,basis,scale,gain):
    index={p:i for i,p in enumerate(ports)};out=np.zeros((basis.shape[1],D),np.float32)
    for slot,symbol in binding:
        start=D+index[freeze(symbol)]*B;decoder=basis[start:start+B].T/scale[start:start+B][None,:]/gain
        out+=decoder@slot_weights(slot)
    return out/np.sqrt(max(1,len(binding)))


def feature(z,q,role,projection,w,xp):
    attached=xp.tanh(xp.matmul(z[:,None,:],projection)[:,0,:])
    raw=xp.concatenate([xp.tanh(z),q,role,attached,q*attached],axis=1)
    return xp.concatenate([xp.ones((len(z),1),dtype=xp.float32),raw,xp.tanh(raw@w)],axis=1)


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('catalog_model',type=Path);p.add_argument('basis',type=Path);p.add_argument('basis_report',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);p.add_argument('--rounds',type=int,default=16);a=p.parse_args()
    if not 1<=a.rounds<=32:raise ValueError('round count outside experiment limits')
    mh=hashlib.sha256(a.manifest.read_bytes()).hexdigest();bh=hashlib.sha256(a.basis.read_bytes()).hexdigest();ch=hashlib.sha256(a.catalog_model.read_bytes()).hexdigest()
    report=json.loads(a.basis_report.read_text());meta=json.loads(gzip.decompress(a.catalog_model.with_suffix('.json.gz').read_bytes()))
    if report['manifest_sha256']!=mh or report['basis_sha256']!=bh or report['model_sha256']!=ch or meta['manifest_sha256']!=mh:raise ValueError('artifact mismatch')
    if not report['active_boundary_weighting'] or not report['numerical_audit']['passed']:raise ValueError('requires audited active-interface basis')
    with np.load(a.basis) as f:basis=f['basis'];scale=f['scale']
    with np.load(a.catalog_model) as f:prototypes=f['prototypes'];pf=f['prototype_families']
    records,_=load_records(json.loads(a.manifest.read_text()));zs=[];ts=[];qs=[];rs=[];ps=[];novels=[];splits=[];bounds=[];gains=[];families=[];expected=[]
    family_ids={f:i for i,f in enumerate(meta['family_names'])};catalog={tuple(v):i for i,v in enumerate(meta['candidate_keys'])}
    for i,r in enumerate(records):
        s=r['sample'];c=s['completion'];ports,mapping,_=output_layout(s['source'],c);bound=state_bound(s['source'],r['rule']);gain=np.float32(np.sqrt(meta['capacity']/max(1,len(ports))))
        source=state(s['source'],ports,meta['capacity'],allow_absent=True).astype(np.float32);target=state(c['facts'],ports,meta['capacity'],mapping).astype(np.float32)
        projected=encode_state(np.stack([source,target]),np.array([bound,bound]),np.array([gain,gain]),basis,scale)
        # Preserve the exact completed-state label obligation from previous probes.
        quotient={freeze(x):freeze(y) for x,y in mapping};again,reason=compose(c['facts'],r['rule'],[(slot,quotient[freeze(v)]) for slot,v in s['binding']],r['tables'])
        if reason or again['novel']:raise ValueError('unproved completed-state control')
        zs.append(projected[0]);ts.append(projected[1]);qs.append(request_with_roles(r['rule'],s['binding'],False));rs.append(request_with_roles(r['rule'],s['binding'],True));ps.append(compile_attachment(ports,s['binding'],basis,scale,gain));novels.append(c['novel']);splits.append(r['split']);bounds.append(bound);gains.append(gain)
        family=family_ids[r['family']];families.append(family);expected.append(catalog[(family,repr(representation(c['facts'],c['source_map'])),repr(ports))])
        if i%250==0:print(json.dumps(dict(encoded=i,total=len(records))),flush=True)
    z,t,q,role,projection=[np.array(v,np.float32) for v in (zs,ts,qs,rs,ps)];split=np.array(splits);novel=np.array(novels,bool);bounds=np.array(bounds,np.float32);gains=np.array(gains,np.float32)
    w=np.random.default_rng(119).normal(0,1/16,(basis.shape[1]+4*D,512)).astype(np.float32)
    x=np.concatenate([feature(z,q,role,projection,w,np),feature(t,q,role,projection,w,np),feature(z,np.zeros_like(q),np.zeros_like(role),np.zeros_like(projection),w,np)])
    y=np.concatenate([np.column_stack([t,novel]),np.column_stack([t,np.zeros(len(z))]),np.column_stack([z,np.zeros(len(z))])]).astype(np.float32)
    partition=np.tile(split,3);loss_scale=np.concatenate([np.full(basis.shape[1],1/np.sqrt(basis.shape[1])),[1]]).astype(np.float32)
    coef,fit=train(x,y*loss_scale,partition=='train',partition=='validation');coef/=loss_scale[None,:]
    with a.model.open('wb') as f:np.savez_compressed(f,w=w,coef=coef,basis=basis,scale=scale)
    mask=split=='test';z=z[mask];t=t[mask];q=q[mask];role=role[mask];projection=projection[mask];bounds=bounds[mask];gains=gains[mask];novel=novel[mask];expected=np.array(expected)[mask];families=np.array(families,np.int32)[mask]
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);gw,gc,gq,gr,gp,gb,gs,gbounds,ggains,gproto,gpf,gfamily=[mx.array(v) for v in (w,coef,q,role,projection,basis,scale,bounds,gains,prototypes,pf,families)]
    def step(current):
        out=feature(current,gq,gr,gp,gw,mx)@gc;emit=out[:,-1]>=.5
        return mx.where(emit[:,None],out[:,:-1],current),emit
    _,oracle_emit=mx.compile(step)(mx.array(t));mx.eval(oracle_emit)
    def rollout(current):
        emitted=[]
        for _ in range(a.rounds):current,emit=step(current);emitted.append(emit)
        decoded=decode_state(current,gbounds,ggains,gb,gs,mx)
        d=mx.where(gfamily[:,None]==gpf[None,:],distances(decoded,gproto,mx),mx.inf)
        return current,mx.stack(emitted),decoded,mx.argmin(d,axis=1)
    final,emissions,decoded,chosen=mx.compile(rollout)(mx.array(z));mx.eval(final,emissions,decoded,chosen)
    final,emissions,decoded,chosen=map(np.array,(final,emissions,decoded,chosen));reference=z.copy();cpu_emissions=[]
    for _ in range(a.rounds):
        out=feature(reference,q,role,projection,w,np)@coef;emit=out[:,-1]>=.5;reference=np.where(emit[:,None],out[:,:-1],reference);cpu_emissions.append(emit)
    decoded_reference=decode_state(reference,bounds,gains,basis,scale,np)
    latent_audit=numerical_audit(final,reference,emissions,np.array(cpu_emissions));full_audit=numerical_audit(decoded,decoded_reference,emissions,np.array(cpu_emissions))
    invalid=np.zeros(len(z),bool);ambiguous=np.zeros(len(z),bool)
    for start in range(0,len(z),128):
        end=min(start+128,len(z));d=distances(decoded[start:end].astype(np.float64),prototypes.astype(np.float64),np);d[families[start:end,None]!=pf[None,:]]=np.inf;best=d.min(1);selected=d[np.arange(end-start),chosen[start:end]]
        invalid[start:end]=selected>best+1e-5;ambiguous[start:end]=(d<=best[:,None]+1e-7).sum(1)>1
    correct=(chosen==expected)&~invalid&~ambiguous;stopped=~emissions[-1]
    result=dict(scope='learned fixed-request latent Cell recurrence, not full successor saturation',manifest_sha256=mh,basis_sha256=bh,catalog_model_sha256=ch,model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),fit=fit,rounds=a.rounds,cases=len(z),latent_width=basis.shape[1],state_readout_shape=list(coef.shape),per_test_projection_floats=int(projection.size),intermediate_full_state_decodes=0,intermediate_cpu_reads=0,backpropagation=False,oracle_completed_false_emissions=int(np.array(oracle_emit).sum()),latent_numerical_audit=latent_audit,decoded_numerical_audit=full_audit,decoder_f64_disagreements=int(invalid.sum()),emissions_per_round=emissions.sum(1).tolist(),exact_target=int(correct.sum()),exact_target_and_stopped=int((correct&stopped).sum()),never_emitted_but_initially_novel=int((novel&~emissions.any(0)).sum()),final_active=int((~stopped).sum()),limitations=['Initial encoding and folded projection compilation still on CPU','Fixed same binding throughout recurrence, not changed successor requests','Catalog contains held-out targets; exact selection is not native semantic proof','Shared latent does not by itself enforce Eq or valid identity','No throughput, ownership or full ruleset support claim'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not latent_audit['passed'] or not full_audit['passed'] or invalid.any():raise SystemExit(1)

if __name__=='__main__':main()
