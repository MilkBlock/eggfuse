"""Cross frozen token models and boundary decoders; never refit on test labels."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from packed_cell_replay import executor,prepare,audit
from token_eq_readout import examples,readout_rows,materialize,expand_scores,check_partition


def verified(path,report,key):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=report[key]:raise ValueError('artifact hash mismatch')
    with np.load(path) as saved:return {k:saved[k] for k in saved.files}


def summarize(rows,scores):
    out=dict(instances=len(rows),query_instances=0,exact_partitions=0,false_merges=0,
        missed_equalities=0,nontransitive=0,closure_false_merges=0)
    offset=0
    for row in rows:
        count=len(row['quotient']['representatives'])
        full=expand_scores(row,scores[offset:offset+count],True,True);offset+=count
        check=check_partition(row['pairs'],row['y'],full)
        out['query_instances']+=int(bool(row['pairs']));out['exact_partitions']+=int(check['exact'])
        for key in ('false_merges','missed_equalities','nontransitive','closure_false_merges'):out[key]+=check[key]
    if offset!=len(scores):raise ValueError('query alignment mismatch')
    return out


def main():
    parser=argparse.ArgumentParser();parser.add_argument('trace',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--variant',nargs=5,action='append',required=True,metavar=('NAME','MODEL','MODEL_REPORT','DECODER','DECODER_REPORT'))
    args=parser.parse_args();raw=read_bytes(args.trace);trace_sha=hashlib.sha256(raw).hexdigest()
    models={};decoders={};provenance={};config=None;w=None
    for name,model_path,model_report_path,decoder_path,decoder_report_path in args.variant:
        if name in models:raise ValueError('duplicate variant')
        report=json.loads(Path(model_report_path).read_text());dreport=json.loads(Path(decoder_report_path).read_text())
        if report['provenance']['test_trace']!=trace_sha or dreport['provenance']!=report['provenance']:raise ValueError('trace provenance mismatch')
        if dreport['model_sha256']!=report['model_sha256']:raise ValueError('decoder parent mismatch')
        model=verified(model_path,report,'model_sha256');decoder=verified(decoder_path,dreport,'decoder_sha256')
        current=(int(model['channels']),bool(model['zero_role_channels']),str(model.get('encoding','slot')))
        if config is not None and config!=current:raise ValueError('incompatible token encodings')
        if not bool(decoder['static_equalities']) or not bool(decoder['quotient']):raise ValueError('quotient decoder required')
        if w is not None and not np.array_equal(w,decoder['w']):raise ValueError('incompatible decoder feature maps')
        config=current;w=decoder['w'];models[name]=model;decoders[name]=decoder
        provenance[name]=dict(model_sha256=report['model_sha256'],decoder_sha256=dreport['decoder_sha256'],train=report['provenance']['train'])
    nodes,rows=examples(json.loads(raw),config[0],config[1],True,config[2]);query=readout_rows(rows,True)
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);plan=prepare(nodes,'two');results={};checks={}
    coefficients=np.concatenate([d['coef'] for d in decoders.values()],axis=1);gc=mx.array(coefficients)
    for name,model in [('oracle',None),*models.items()]:
        tokens=np.array([n['target'] for n in nodes]) if model is None else np.array(executor(nodes,model['w'],model['coef'],plan,True)())
        matrix,_=materialize(query,tokens,w,True);parts=[]
        for start in range(0,len(matrix),4096):
            result=mx.array(matrix[start:start+4096])@gc;mx.eval(result);parts.append(np.array(result))
        scores=np.concatenate(parts);reference=matrix@coefficients;check=audit(scores,reference)
        check['threshold_disagreements']=int(((scores>=.5)!=(reference>=.5)).sum());checks[name]=check
        results[name]={decoder:summarize(rows,scores[:,i]) for i,decoder in enumerate(decoders)}
    report=dict(scope='frozen model/decoder cross audit on fixed full test population',trace_sha256=trace_sha,
        provenance=provenance,encoding=config[2],results=results,numerical_audits=checks,refitting=False,
        union_authorized=False,limitations=['Eq partition only; no scalar, ownership or native semantic certification',
            'Observed CPU matches and routes supplied; no autonomous token generation',
            'Cross comparisons diagnose this held-out workload, not a validation-selected deployment'])
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    if not all(c['passed'] and not c['threshold_disagreements'] for c in checks.values()):raise SystemExit(1)

if __name__=='__main__':main()
