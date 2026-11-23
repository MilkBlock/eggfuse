"""Measure complete-binding assist and select a neural read order on separate programs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

from alternate_proofs import digest
from assist_domain_audit import audit
from higher_cell import read
from layout_credit_report import verify
from marginal_policy import splits


def control(folder,binary):
    tape=read(folder/'tape.json')
    program=folder/'program.json'
    if tape['program_sha256']!=digest(program):
        raise ValueError('teacher tape is from another program')
    source,replay=[json.loads(subprocess.check_output([binary,mode,program,folder/'tape.json','audit']))
                   for mode in ('reference','replay')]
    if any(source[k]!=replay[k] for k in ('schedule','state_sha','rhs','writes','resumes','events')):
        raise ValueError('teacher replay diverged')
    full=audit(folder,binary,tape['requests'],'audit')
    if (full['counts']['accepted']!=source['matches'] or full['assist']['residual_commits']
            or full['state_sha']!=source['state_sha'] or replay['counts']['accepted']!=full['commits']):
        raise ValueError('teacher did not cover all distinct commits')
    return dict(mode='teacher control',binary=digest(binary),program=digest(program),tape=digest(folder/'tape.json'),
                required=source['matches'],nonempty_rule_runs=len({(r['run'],r['rule']) for r in tape['requests']}),
                exact_candidates=source['residual_candidates'],exclusive_teacher_candidates=replay['residual_candidates'],
                assist=full)


def selection(proto,corpus,out):
    cfg=splits(proto)
    identity={}
    results={}
    for arm in cfg['arms']:
        rows={}
        for name,fingerprint in cfg['validation'].items():
            case=corpus/name
            assist=out/'validation'/arm/(name+'.json')
            exclusive=out/'exclusive'/arm/(name+'.json')
            a,e=read(assist),read(exclusive)
            mode='source' if arm=='source' else 'connected'
            checkpoint=a['recovery']['checkpoint']
            settings=[a[k] for k in ('actor','catalog','reader','field_reader','policy','binary','seed','program','tape')]
            if (identity.setdefault(name,settings)!=settings or a['program']!=name or a['mode']!='native assist'
                    or e['case']!=name or e['mode']!='exclusive' or e['independent_search_calls']!=0
                    or any(a[k]!=e[k] for k in ('actor','field_reader','binary','catalog'))
                    or a.get('read_order','source')!=mode or e['read_order']!=mode or e['recovery']!=checkpoint
                    or digest(case/'program.json')!=fingerprint or digest(case/'tape.json')!=a['tape']):
                raise ValueError('misaligned inputs, mode or pointer settings')
            verify(a,read(case/'exact.json'))
            xs=a['recall_by_rule_run']
            ref=Counter((q['run'],q['rule']) for q in read(case/'tape.json')['requests'])
            if (len(xs)!=len(ref) or {(r,i):n for r,i,_,n in xs}!=ref or
                any(not 0<=k<=n for _,_,k,n in xs)):
                raise ValueError('invalid teacher rule-Run denominator')
            work=a['execution']
            signed=sum(x[2] for x in xs)
            if signed!=work['counts']['accepted'] or sum(ref.values())!=a['reference_commits']:
                raise ValueError('signed group totals disagree')
            changed=sum(v.get('changed_read_position',0) for v in work['partial_proof_counts'].values())
            if bool(changed)!=(mode=='connected'):
                raise ValueError('declared read order absent from the evaluated frontier')
            rows[name]=dict(checkpoint=checkpoint,signed=signed,reference=a['reference_commits'],paid=work['issued'],
                duplicates=work['counts']['duplicates'],missed=a['reference_commits']-signed,
                complete=sum(k==n for _,_,k,n in xs),total=len(xs),complete_runs=sum(k==n for _,k,n in a['recall_by_nonempty_run']),
                changed_positions=changed,common=e['common_runs'],final_equal=e['final_equal'],
                held_issued=a['held_issued'],held_complete=a['held_complete'],candidate_work=a['candidate_work'],
                signed_ops=sum(work['ept']['signed_external']+work['ept']['signed_internal']),
                assist_sha=digest(assist),exclusive_sha=digest(exclusive))
        results[arm]=rows
    refit=read(out/'model'/'training.json')
    if ({k:v['program'] for k,v in refit['training'].items()} != cfg['train'] or
        refit['read_order'] != 'connected' or refit['head'] != digest(out/'model'/'head.pt')):
        raise ValueError('refit head differs from the declared training split')
    for name in cfg['validation']:
        if (results['connected'][name]['checkpoint'] != results['source'][name]['checkpoint'] or
            results['refit'][name]['checkpoint'] != refit['head']):
            raise ValueError('recovery head does not match the ablation')
    base=results['source']
    def score(rows):
        return (min(v['common'] for v in rows.values()),sum(v['complete'] for v in rows.values()),
                sum(v['signed'] for v in rows.values()),-sum(v['paid'] for v in rows.values()))
    eligible=['source']
    _, base_groups, base_hits, negative_base_cost = score(base)
    for arm, rows in results.items():
        _, groups, hits, negative_cost = score(rows)
        affordable = (-negative_cost) * base_hits <= (-negative_base_cost) * hits
        preserves_prefixes = all(v['common'] >= base[n]['common'] for n, v in rows.items())
        if groups > base_groups and hits >= base_hits and affordable and preserves_prefixes:
            eligible.append(arm)
    winner=max(eligible,key=lambda a:score(results[a]))
    return dict(protocol=digest(proto),selected=winner,eligible=eligible,programs=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    actions=p.add_subparsers(dest='action',required=True)
    for cmd,keys in [('control',('folder','binary','output')),('select',('protocol','corpus','results','output'))]:
        sub=actions.add_parser(cmd)
        for k in keys:
            sub.add_argument(k,type=Path)
    a=p.parse_args()
    result=control(a.folder,a.binary) if a.action=='control' else selection(a.protocol,a.corpus,a.results)
    if a.action=='select' and a.output.exists() and read(a.output)!=result:
        raise ValueError('existing selection lock differs')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
