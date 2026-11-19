"""Execute distinct formal source programs in the Cell runtime and map them to all rows."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from source import HERE, PRODUCERS, canonical_hash, check, digest, normalize, run_batch


def event_list(raw):
    if raw.ndim!=3 or raw.shape[0]!=3 or raw.shape[-1]!=3 or raw.dtype.kind not in 'iu':
        raise ValueError('expected [3 waves,capacity,kind/key/value] per graph')
    result=[]
    for wave,frames in enumerate(raw):
        for kind,k,v in frames.tolist():
            if kind==0:continue
            check(1<=kind<=3,'unsupported physical producer')
            result.append((wave,PRODUCERS[kind-1],k,v))
    return result


def source_truth(raw):
    by_key={name:{} for name in PRODUCERS};waves=[]
    for wave in raw:
        for kind,k,v in wave.tolist():
            if kind==0:continue
            table=by_key[PRODUCERS[kind-1]]
            check(table.setdefault(k,v)==v,'consumer fixture requires single value per source kind and key')
        c=sorted((k,x,by_key['P1'][k]) for k,x in by_key['P0'].items() if k in by_key['P1'])
        unary=sorted(by_key['U'].items())
        waves.append(dict(C=c,V=unary))
    return waves


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('executable',type=Path)
    parser.add_argument('evidence_root',type=Path)
    parser.add_argument('--splits',nargs='+',default=('iid','heldout'),choices=('train','iid','heldout'))
    args=parser.parse_args()
    sys.path.insert(0,str(HERE.parent))
    from data import dataset, source_rows
    panels={name:dataset(name) for name in args.splits}
    unique={};indices={}
    for split,panel in panels.items():
        refs=[]
        for raw in panel['events']:
            events=normalize(event_list(raw));key=canonical_hash(events)
            if key in unique:check(unique[key]==events,'input hash collision')
            else:unique[key]=events
            refs.append(key)
        indices[split]=refs
    args.evidence_root.mkdir(exist_ok=True,parents=True)
    reports,plan=run_batch(args.executable.resolve(),unique)
    saved_plan=json.loads((HERE/'plan.json').read_text())
    check(plan==saved_plan['rules'],'panel changes the neural projection recipe')
    verified={r['id']:r for r in reports};summaries={}
    for split,panel in panels.items():
        rhs=Counter();effective=Counter();final_count=Counter();nonempty=Counter();duplicates=0;signatures=hashlib.sha256()
        for i,raw in enumerate(panel['events']):
            r=verified[indices[split][i]]; expected=source_truth(raw)
            for wave,targets in enumerate(expected):
                actual=r['runs'][wave]
                check(actual['ready_sha256']==canonical_hash(targets),f'{split} graph {i} source readiness mismatch at wave {wave}')
            check(r['runs'][3]['ready_sha256']==canonical_hash(expected[-1]),'finish changed producers')
            reference=source_rows(raw,panel['seal'][i])
            check(canonical_hash(reference['finish_witnesses'])==r['finish_witnesses_sha256'], f'{split}[{i}] finish parent identities or first-visible wave differ')
            for s,source_run in zip(r['runs'],reference['runs']):
                check(s['ordinal']==source_run['ordinal'],'source Run ordinals disagree')
                for name,hash_field in [('rhs','rhs_outputs_sha256'),('effective_writes','delta_sha256')]:
                    facts=sorted((table,tuple(values)) for table,rows in source_run[name].items() for values in rows)
                    check(canonical_hash(facts)==s[hash_field],f'{split}[{i}] differs in {name} at Run {s["ordinal"]}')
                public={k:sorted(map(tuple,source_run['visible'].get(k,()))) for k in ('P0','P1','U','C','V')}
                check(canonical_hash(public)==s['visible_public_sha256'],f'{split}[{i}] public snapshot mismatch')
                rhs[s['ruleset']]+=s['executed_bindings'];effective[s['ruleset']]+=s['actual_publications']
                if s['ruleset']!='finish':duplicates+=s['executed_bindings']-s['actual_publications']
            for k,rows in expected[-1].items():final_count[k]+=len(rows);nonempty[k]+=bool(rows)
            signatures.update(canonical_hash([indices[split][i],r['runs'],r['final_semantic_sha256'],r['final_physical_sha256']]).encode())
        summaries[split]=dict(graphs=len(panel['events']),unique_source_schedules=len(set(indices[split])),
                              rhs_bindings_by_run=dict(rhs),effective_publications_by_run=dict(effective),
                              repeated_bindings_to_already_published=duplicates,final_row_counts=dict(final_count),
                              nonempty_graphs_per_relation=dict(nonempty),ordered_execution_evidence_sha256=signatures.hexdigest(),
                              raw_tensor_sha256=digest(np.ascontiguousarray(panel['events']).tobytes()))
    evidence=dict(cases=reports,graph_to_source=indices)
    path=args.evidence_root/'cell-cpu-source-replay.json';path.write_text(json.dumps(evidence,separators=(',',':'))+'\n')
    summary=dict(status='pass',source_semantics='three producer Runs then shared finish',distinct_sources=len(reports),
                 distinct_executed_runs=4*len(reports),panels=summaries,source_program_sha256=digest((HERE/'rules.egg').read_bytes()),
                 binary_sha256=digest(args.executable.read_bytes()),input_generator_sha256=digest((HERE.parent/'data.py').read_bytes()),
                 full_evidence_path=str(path),full_evidence_sha256=digest(path.read_bytes()))
    (HERE/'panel-audit.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
