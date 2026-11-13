"""Frozen Eq readout on actual GPU joint-match samples and CPU-derived labels."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from token_eq_readout import pair_layout,static_equalities,quotient_layout,readout_rows,materialize
from audit_training_expansion import summarize


def rows_from_labels(recipe,rules,labels):
    if len(rules)!=len(labels):raise ValueError('label alignment')
    rows=[]
    for index,(rid,classes) in enumerate(zip(rules,labels)):
        rule=recipe['rules'][int(rid)];pairs,q,s,d,p=pair_layout(rule)
        if any(a>=len(classes) or b>=len(classes) or classes[a]<0 or classes[b]<0 for a,b in pairs):raise ValueError('missing CPU Eq label')
        y=np.array([classes[a]==classes[b] for a,b in pairs],bool);static=static_equalities(rule,pairs)
        if (static&~y).any():raise ValueError('CPU label contradicts static equality')
        rows.append(dict(index=index,pairs=pairs,q=q,s=s,d=d,p=p,y=y,static=static,quotient=quotient_layout(rule,pairs,static)))
    return rows


def main():
    p=argparse.ArgumentParser()
    for key in ('capture','decoder','decoder_report','output'):p.add_argument(key,type=Path)
    a=p.parse_args();started=time.monotonic();meta=json.loads(a.capture.with_suffix('.json').read_text());report=json.loads(a.decoder_report.read_text())
    if hashlib.sha256(a.capture.read_bytes()).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('capture hash')
    if meta['capture']['schema']!='device-joint-witness/v2' or not meta['capture']['passed']:raise ValueError('unverified target capture')
    if hashlib.sha256(a.decoder.read_bytes()).hexdigest()!=report['weights_sha256']:raise ValueError('decoder hash')
    if meta['model_sha256']!=report['model_sha256']:raise ValueError('decoder parent model mismatch')
    with np.load(a.capture) as data:
        ids=[meta['source_rules'].index(int(r)) for r in data['rules']]
        rows=rows_from_labels(meta['recipe'],ids,data['target_eq_classes'])
        targets=data['targets'];predicted=data['predicted_tokens']
        label_stats=dict(full_pair_queries=sum(len(r['pairs']) for r in rows),static_equalities=sum(int(r['static'].sum()) for r in rows),
            dynamic_quotient_queries=sum(len(r['quotient']['representatives']) for r in rows),dynamic_true_equalities=sum(int(r['y'][r['quotient']['representatives']].sum()) for r in rows),
            distinct_rule_partitions=len({(int(rid),tuple(classes)) for rid,classes in zip(data['rules'],data['target_eq_classes'])}))
    if len(rows)!=meta['capture']['samples'] or len(targets)!=len(rows) or len(predicted)!=len(rows):raise ValueError('sample alignment')
    with np.load(a.decoder) as data:weights={k:data[k] for k in data.files}
    index=np.flatnonzero(weights['alphas']==report['selected']['partition'])
    if len(index)!=1:raise ValueError('decoder selection')
    coef=weights['coef'][:,index];result={}
    for name,tokens in [('cpu_target_token',targets),('gpu_predicted_token',predicted)]:
        features,_=materialize(readout_rows(rows,True),tokens,weights['w'],True)
        result[name]=summarize(rows,(features@coef).reshape(-1))
    out=dict(scope='actual selected-family GPU token Eq readout; no fitting or union authorization',case=meta['capture']['case'],partition=meta['capture']['partition'],
        capture_sha256=meta['capture']['artifact_sha256'],adapter_sha256=meta.get('adapter_sha256'),inference_coefficients_sha256=meta.get('inference_coefficients_sha256'),decoder_sha256=report['weights_sha256'],label_statistics=label_stats,results=result,
        cpu_readout_audit_seconds=time.monotonic()-started,backpropagation=False,union_authorized=False,
        limitations=['Small selected immutable Cell family, not full Eggcc','Exact execution establishes completion; ridge is audited separately','Test samples must not be used for fitting'])
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
