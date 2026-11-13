"""Train-only joint body/boundary basis viability, not learned completion."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from corpus_cell_ridge import load_records,distances,initial_attachment
from boundary_cell_ridge import D,state,output_layout
from corpus_repeat_probe import state_bound
from bounded_cell_readout import normalize
from decode_cell_completion import representation


def fit_basis(training,rank,seed=271):
    if not 1<=rank<=min(training.shape):raise ValueError('rank exceeds training dimensions')
    sketch=min(rank+16,min(training.shape));rng=np.random.default_rng(seed)
    omega=rng.normal(size=(training.shape[1],sketch)).astype(np.float32)
    q,_=np.linalg.qr(training@omega,mode='reduced')
    # One power iteration improves the approximation; no targets outside train.
    q,_=np.linalg.qr(training@(training.T@q),mode='reduced')
    _,singular,vt=np.linalg.svd(q.T@training,full_matrices=False)
    return vt[:rank].T.astype(np.float32),singular[:rank]


def restore(unit,bounds,xp):
    return xp.concatenate([unit[:,:D]*bounds[:,None],unit[:,D:]],axis=1)


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);p.add_argument('--rank',type=int,default=128);p.add_argument('--basis-output',type=Path,required=True);p.add_argument('--active-boundary-weighting',action='store_true');a=p.parse_args()
    meta=json.loads(gzip.decompress(a.model.with_suffix('.json.gz').read_bytes()));mh=hashlib.sha256(a.manifest.read_bytes()).hexdigest()
    if meta['manifest_sha256']!=mh:raise ValueError('manifest mismatch')
    records,_=load_records(json.loads(a.manifest.read_text()));train=[];train_gains=[];gains=[];targets=[];bounds=[];splits=[];expected=[];families=[];interfaces=[]
    family_ids={f:i for i,f in enumerate(meta['family_names'])};catalog={tuple(v):i for i,v in enumerate(meta['candidate_keys'])}
    for r in records:
        s=r['sample'];c=s['completion'];ports,mapping,_=output_layout(s['source'],c);bound=np.array([state_bound(s['source'],r['rule'])],np.float32)
        gain=np.float32(np.sqrt(meta['capacity']/max(1,len(ports)))) if a.active_boundary_weighting else np.float32(1)
        target=state(c['facts'],ports,meta['capacity'],mapping).astype(np.float32)
        if r['split']=='train':
            source=state(s['source'],ports,meta['capacity'],allow_absent=True).astype(np.float32)
            train_gains.extend([gain,gain]);train.extend([normalize(source[None,:],bound,np)[0],normalize(target[None,:],bound,np)[0]])
        else:
            gains.append(gain);interfaces.append((ports,s['binding']));targets.append(target);bounds.append(bound[0]);splits.append(r['split']);family=family_ids[r['family']];families.append(family)
            expected.append(catalog[(family,repr(representation(c['facts'],c['source_map'])),repr(ports))])
    training=np.array(train,np.float32);scale=np.concatenate([np.full(D,1/np.sqrt(D)),np.full(training.shape[1]-D,1/np.sqrt(training.shape[1]-D))]).astype(np.float32)
    training[:,D:]*=np.array(train_gains,np.float32)[:,None]
    print(json.dumps(dict(training_rows=len(training),state_width=training.shape[1],rank=a.rank)),flush=True)
    basis,singular=fit_basis(training*scale,a.rank)
    with a.basis_output.open('wb') as f:np.savez_compressed(f,basis=basis,scale=scale,singular=singular)
    targets=np.array(targets,np.float32);bounds=np.array(bounds,np.float32);split=np.array(splits);family=np.array(families);expected=np.array(expected)
    weighted=normalize(targets,bounds,np)*scale;gains=np.array(gains,np.float32);weighted[:,D:]*=gains[:,None]
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);gb,gs,gscale=mx.array(basis),mx.array(bounds),mx.array(scale)
    gg=mx.array(gains)
    def roundtrip(v):
        unit=((v@gb)@gb.T)/gscale
        unit=mx.concatenate([unit[:,:D],unit[:,D:]/gg[:,None]],axis=1)
        return restore(unit,gs,mx)
    actual=mx.compile(roundtrip)(mx.array(weighted));mx.eval(actual);actual=np.array(actual)
    unit=((weighted@basis)@basis.T)/scale;unit[:,D:]/=gains[:,None]
    reference=restore(unit,bounds,np)
    finite=np.isfinite(actual).all() and np.isfinite(reference).all();outside=int(np.count_nonzero(np.abs(actual-reference)>.002+.004*np.abs(reference)))
    with np.load(a.model) as saved:prototypes=saved['prototypes'].astype(np.float64);pf=saved['prototype_families']
    def select(values):
        chosen=[];ambiguous=[]
        for start in range(0,len(values),128):
            end=min(start+128,len(values));d=distances(values[start:end].astype(np.float64),prototypes,np);d[family[start:end,None]!=pf[None,:]]=np.inf
            best=d.min(1);chosen.extend(np.argmin(d,axis=1).tolist());ambiguous.extend(((d<=best[:,None]+1e-7).sum(1)>1).tolist())
        ambiguous=np.array(ambiguous)
        return (np.array(chosen)==expected)&~ambiguous,ambiguous
    correct,ambiguous=select(actual);original,original_ambiguous=select(targets);reports={}
    active_squared=[];active_counts=[];attachment_errors=[]
    for i,(ports,binding) in enumerate(interfaces):
        width=len(ports)*16;delta=actual[i,D:D+width]-targets[i,D:D+width]
        active_squared.append(float(np.sum(delta.astype(np.float64)**2)));active_counts.append(width)
        delta=initial_attachment(actual[i],ports,binding)-initial_attachment(targets[i],ports,binding)
        attachment_errors.append(float(np.mean(delta.astype(np.float64)**2)))
    active_squared=np.array(active_squared);active_counts=np.array(active_counts);attachment_errors=np.array(attachment_errors)
    for part in ('validation','test'):
        mask=split==part
        reports[part]=dict(cases=int(mask.sum()),oracle_uncompressed_exact_target=int((mask&original).sum()),lost_original_targets=int((mask&original&~correct).sum()),oracle_compressed_exact_target=int((mask&correct).sum()),ambiguous=int((mask&np.array(ambiguous)).sum()),body_rmse=float(np.sqrt(np.mean((actual[mask,:D]-targets[mask,:D])**2))),boundary_rmse=float(np.sqrt(np.mean((actual[mask,D:]-targets[mask,D:])**2))),active_boundary_rmse=float(np.sqrt(active_squared[mask].sum()/max(1,active_counts[mask].sum()))),query_attachment_rmse=float(np.sqrt(attachment_errors[mask].mean())),boundary_max_abs=float(np.abs(actual[mask,D:]).max()))
    result=dict(scope='oracle joint-state compression viability, not ridge completion or a runtime',manifest_sha256=mh,model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),basis_sha256=hashlib.sha256(a.basis_output.read_bytes()).hexdigest(),training_rows=len(training),rank=a.rank,active_boundary_weighting=a.active_boundary_weighting,state_width=training.shape[1],basis_source='train source and completed states only, randomized uncentered SVD with one power iteration',numerical_audit=dict(passed=bool(finite and outside==0),nonfinite=not bool(finite),coordinates_outside_tolerance=outside),reports=reports,limitations=['True completed state supplied for compression; no prediction or stopping evaluated','Known candidate dictionary includes held-out states','One basis does not prove an information-theoretic bound','No exact identity, visibility, successor or ownership proof'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not finite or outside:raise SystemExit(1)

if __name__=='__main__':main()
