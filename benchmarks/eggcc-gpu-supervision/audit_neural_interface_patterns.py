"""Exhaustive finite interface-head check, not a general neural runtime proof."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from neural_typed_patterns import typed_candidates
from neural_ordered_relations import ordered_model


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    source=json.loads(a.trace.read_text());source=source.get('recipe',source)
    recipe=dict(source,rules=[r for r in source['rules'] if r['metadata']['source_set']=='context'])
    data,coverage=typed_candidates(recipe,(0,),ordered=True)
    signatures,indices,inverse=np.unique(data['relations'],axis=0,return_index=True,return_inverse=True)
    labels=data['valid'][indices]
    if not np.array_equal(labels[inverse],data['valid']):raise ValueError('same interface has conflicting labels')
    model=ordered_model(data['x'].shape[-1],signatures.shape[-1],True);model.load_weights(str(a.weights))
    results=[];scores=[]
    for batch in (1,64,256):
        parts=[]
        for start in range(0,len(signatures),batch):
            h=model.relation(mx.array(signatures[start:start+batch]))
            parts.append(np.array(model.match_relation(h)[:,0]))
        score=np.concatenate(parts);scores.append(score)
        signed=score*np.where(labels>0,1,-1)
        results.append(dict(batch=batch,correct=int(((score>=0)==labels).sum()),finite=bool(np.isfinite(score).all()),minimum_signed_logit=float(signed.min())))
    passed=all(r['finite'] and r['correct']==len(labels) and r['minimum_signed_logit']>0 for r in results)
    report=dict(status='pass' if passed else 'difference',scope='all enumerated typed slot-only query-interface signatures for the 17 context rules; not arbitrary scalar guards, liveness, routing or token semantics',raw_typed_partitions=sum(r['enumerated_patterns_with_scalar_variants'] for r in coverage),distinct_interface_signatures=len(signatures),positive_signatures=int(labels.sum()),negative_signatures=int((labels==0).sum()),batches=results,maximum_batch_logit_difference=float(max(np.max(np.abs(s-scores[0])) for s in scores)),coverage=coverage,weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),relation_signatures_sha256=hashlib.sha256(signatures.tobytes()).hexdigest(),formal_roundoff_bound=False)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='coverage'}))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
