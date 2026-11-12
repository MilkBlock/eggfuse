"""Ridge recognition of shared completion templates from held entrance DAGs.

No backpropagation. Candidate prediction is NOT permission to publish effects.
"""
import argparse
import collections
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from dataset import extension,digest

OPS=['Input','Get','Single','SubTuple','Concat']


class Encoder:
    def __init__(self, seed=20261115):
        rng=np.random.default_rng(seed);self.d=32
        self.operator=rng.normal(0,.4,(5,32)).astype(np.float32)
        self.position=rng.normal(0,.12,(3,32,32)).astype(np.float32)
        self.literal=rng.normal(0,.25,(3,3,32)).astype(np.float32)

    def __call__(self,nodes):
        hidden=[];used=set();counts=np.zeros(5,np.float32);scalar=[]
        for facts in nodes:
            value=np.zeros(32,np.float32)
            for table,args in facts:
                op=OPS.index(table);counts[op]+=1;v=self.operator[op].copy()
                for pos,(kind,sort,x) in enumerate(args):
                    if kind=='eq':v+=hidden[x]@self.position[pos];used.add(x)
                    else:
                        v+=np.array([float(x)/4,np.sin(float(x)),np.cos(float(x))],np.float32)@self.literal[pos]
                        scalar.append(float(x))
                value+=np.tanh(v)
            hidden.append(value)
        h=np.asarray(hidden);roots=[i for i in range(len(nodes)) if i not in used]
        return np.concatenate([h.sum(0),h.max(0),h[roots].sum(0),counts,
                               [len(nodes),len(roots),sum(scalar),sum(x*x for x in scalar)]]).astype(np.float32)


def field_moments(nodes):
    """Cheap typed-slot summaries; no rule application or closure in encoding."""
    scalar=collections.defaultdict(list);links=collections.defaultdict(list)
    counts=collections.Counter()
    for facts in nodes:
        for table,args in facts:
            counts[table]+=1
            for pos,(kind,sort,value) in enumerate(args):
                (scalar if kind=='literal' else links)[table,pos].append(value)
    out=[len(nodes)]+[counts[t] for t in OPS]
    for table in OPS:
        for pos in range(3):
            values=scalar[table,pos];edges=links[table,pos]
            out.extend([len(values),sum(values),sum(v*v for v in values),min(values,default=0),max(values,default=0),
                        len(edges),len(set(edges))])
    return np.array(out,dtype=np.float32)


def fit(x,y,regularization):
    x,y=x.astype(np.float64),y.astype(np.float64)
    mean=x.mean(0);scale=np.maximum(x.std(0),.05);ym=y.mean(0);z=(x-mean)/scale
    if len(z)<z.shape[1]:w=z.T@np.linalg.solve(z@z.T+regularization*np.eye(len(z)),y-ym)
    else:w=np.linalg.solve(z.T@z+regularization*np.eye(z.shape[1]),z.T@(y-ym))
    w/=scale[:,None]
    return w.astype(np.float32),(ym-mean@w).astype(np.float32)


def features(x,kind,centers,projection,bias):
    if kind=='linear':return x
    if kind=='quadratic':return np.concatenate([x,(1+x@centers.T/x.shape[1])**2],1)
    if kind=='radial':
        dist=np.maximum((x*x).sum(1)[:,None]+(centers*centers).sum(1)-2*x@centers.T,0)
        return np.concatenate([x,np.exp(-dist/x.shape[1])],1)
    return np.concatenate([x,np.tanh(x@projection+bias)],1)


def main():
    p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--encoder-seeds',default='20261115')
    p.add_argument('--field-moments',action='store_true');p.add_argument('--moments-only',action='store_true')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    corpus=json.loads(args.corpus.read_text());rows=corpus['records']
    seeds=[int(s) for s in args.encoder_seeds.split(',')];encoders=[Encoder(seed) for seed in seeds]
    if args.moments_only:encoders=[]
    use_moments=args.field_moments or args.moments_only
    start=time.perf_counter();raw=np.array([np.concatenate([encoder(r['entry']) for encoder in encoders]+
        ([field_moments(r['entry'])] if use_moments else [])) for r in rows]);encode_time=time.perf_counter()-start
    masks={s:np.array([r['split']==s for r in rows]) for s in ('train','validation','test')}
    for a,b in (('train','validation'),('train','test'),('validation','test')):
        assert {r['skeleton_key'] for r in rows if r['split']==a}.isdisjoint(r['skeleton_key'] for r in rows if r['split']==b)
    catalog={r['completion_key']:r['completion'] for r in rows if r['split']=='train'}
    labels=sorted(catalog);target=np.array([labels.index(r['completion_key']) for r in rows])
    # Dense orthogonal target codes, with a categorical readout onto the known
    # completion catalog. This is template recognition, not latent-state lookup.
    rng=np.random.default_rng(1307);codes=np.linalg.qr(rng.normal(size=(len(labels),len(labels))))[0].astype(np.float32)
    mean=raw[masks['train']].mean(0);scale=np.maximum(raw[masks['train']].std(0),.05)
    x=(raw-mean)/scale;centers=x[masks['train']]
    projection=rng.normal(0,np.sqrt(1/x.shape[1]),(x.shape[1],256)).astype(np.float32)
    bias=rng.uniform(-1,1,256).astype(np.float32)
    logs=[];best=None
    for kind in ('linear','quadratic','radial','tanh'):
        ff=features(x,kind,centers,projection,bias)
        for reg in (.001,.1,10.):
            w,b=fit(ff[masks['train']],codes[target[masks['train']]],reg)
            scores=(ff[masks['validation']]@w+b)@codes.T
            predicted=scores.argmax(1);truth=target[masks['validation']]
            hit=predicted==truth
            macro=np.mean([hit[truth==c].mean() for c in np.unique(truth)])
            row=dict(kind=kind,reg=reg,validation_correct=int(hit.sum()),validation_total=len(hit),validation_macro=float(macro))
            logs.append(row);print(row,flush=True);quality=(macro,hit.mean())
            if best is None or quality>best[0]:
                best=(quality,row,kind,w,b)
    _,selection,kind,w,b=best
    ff=features(x,kind,centers,projection,bias)
    scores=(ff@w+b)@codes.T;predicted=scores.argmax(1)
    test=masks['test'];truth=target[test];guess=predicted[test];hit=guess==truth
    test_rows=[r for r in rows if r['split']=='test'];details=[]
    train_entries={r['entry_key'] for r in rows if r['split']=='train'}
    lookup_hits=sum(r['entry_key'] in train_entries for r in test_rows)
    assert lookup_hits==0
    for r,choice,correct in zip(test_rows,guess,hit):
        mapped=extension(r['entry'],catalog[labels[choice]])
        if correct:assert mapped==[tuple(p) for p in r['actual_port_map']]
        details.append(dict(id=r['id'],expected=r['completion_key'],predicted=labels[choice],correct=bool(correct),
                            necessary_containment_pass=mapped is not None,
                            actual_port_mapping_equal=mapped==[tuple(p) for p in r['actual_port_map']],
                            predicted_port_map=mapped))
    # Reject containment-as-proof: an unsupported extra fact preserves all
    # input facts but is not the actual saturated completion.
    sample=test_rows[0];superset=sample['completion']+[[['Input',[['literal','i64',999999]]]]]
    assert extension(sample['entry'],superset) is not None and superset!=sample['completion']
    majority=collections.Counter(target[masks['train']]).most_common(1)[0][0]
    # Cold structural extraction vs already-batched numeric inference are
    # explicitly separated; neither is an end-to-end speed comparison.
    start=time.perf_counter()
    for _ in range(20):
        measured=(features(x[test],kind,centers,projection,bias)@w+b)@codes.T
    numeric_ms=(time.perf_counter()-start)*1000/20
    np.savez(args.output/'model.npz',mean=mean,scale=scale,codes=codes,centers=centers,
             projection=projection,bias=bias,w=w,b=b,kind=kind,labels=np.array(labels),encoder_seeds=np.array(seeds if encoders else [],dtype=np.int64),field_moments=use_moments,
             catalog_sha256=digest(catalog),encoder_schema='entry-projection/v1')
    result=dict(scope='Actual Cell/native-generated bounded multi-entry completion recognition; no effect takeover',
                corpus_summary=corpus['summary'],selection=selection,validation=logs,
                test=dict(correct=int(hit.sum()),total=len(hit),accuracy=float(hit.mean()),
                          macro=float(np.mean([hit[truth==c].mean() for c in np.unique(truth)])),
                          top3_correct=int(np.sum([t in np.argsort(s)[-3:] for t,s in zip(truth,scores[test])])),
                          majority_correct=int((truth==majority).sum()),
                          exact_entry_lookup_hits=lookup_hits,
                          wrong_candidates_passing_containment=sum(not d['correct'] and d['necessary_containment_pass'] for d in details)),
                encoder_seeds=seeds if encoders else [],field_moments=use_moments,feature_dimensions=int(x.shape[1]),numeric_feature_dimensions=int(ff.shape[1]),
                costs=dict(cold_python_encoding_ms_total=encode_time*1000,encoded_entries=len(rows),
                           cached_numeric_batch_ms=numeric_ms,batch_rows=int(test.sum()),
                           scope='standalone CPU diagnostic; excludes routing, proof checks, copying and publication; not GPU or runtime speedup'),
                negative_superset_containment_passes_but_not_completion=True,
                runtime_takeover=False,backpropagation=False,details=details,
                corpus_sha256=hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (args.output/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    print('RESULT',selection,result['test'],result['costs'])


if __name__=='__main__':main()
