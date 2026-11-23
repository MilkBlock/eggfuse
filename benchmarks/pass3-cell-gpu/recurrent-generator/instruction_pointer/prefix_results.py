"""Compare exact native winner identities across capped and partial-verification arms."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def run_counts(rows):
    result=Counter()
    recalls=[]
    for row in rows.values():
        n,h=row['required'],row['recovered']
        if len(set(row['winner_ids']))!=h:
            raise ValueError('duplicate winner in native ledger')
        issued=row.get('issued',0)
        matches=row.get('verified_matches',0)
        result.update(required=n, recovered=h, residual=n-h, issued=issued, duplicates=matches-h,
                      rejected_or_off_reference=issued-matches)
        if n:
            recalls.append(h/n)
            result['complete_nonempty']+=int(h==n)
    return dict(**result,macro_recall=sum(recalls)/len(recalls),nonempty=len(recalls))


def summarize(source,out,uncapped_reference):
    out.mkdir(parents=True,exist_ok=True)
    replay=read(source/'receiver-replay.json')
    if read(source/'sum-semantic.json')['status']!='pass':
        raise ValueError('sum-bits proof failure')
    build=replay['receiver_sha256']
    weights=read(source/'loopfact-anchor.json')['weights_sha256']
    summary=dict(receiver_control=replay,weights_sha256=weights,mode='shadow',cpu_inference_threads=1,
                 top_k=32,proofs={},holdouts={},anchor={},profile={},cases={})
    control=read(uncapped_reference/'summary.json')['arms']['disagreement']
    if control['training']['weights_sha256']!=weights:
        raise ValueError('wrong frozen parent weights')
    smoke=read(source/'smoke.json')
    if smoke['receiver_sha256']!=build or smoke['issued'] or smoke['checks']!=5:
        raise ValueError('partial request isolation regression')
    summary['native_protocol_smoke']=smoke
    for name in ('fact','loopfact','sum-divisors'):
        result={}
        by_run={}
        for mode in ('free','cap','safe'):
            wrapper=read(source/f'{name}-all-{mode}.json')
            x=wrapper['result']
            if (wrapper['weights_sha256']!=weights or wrapper['receiver_sha256']!=build or x['independent_search_calls']
                    or x['mode']!='shadow' or x['state_sha']!=replay['programs'][name]['state_sha']):
                raise ValueError('unmatched native shadow')
            if wrapper['policy']!=dict(top_k=None if mode=='free' else 32,verify=mode=='safe',audit=False):
                raise ValueError('different policy treatment')
            rows=x.pop('by_run')
            if x['runs']!=len(rows) or len(rows)!=replay['programs'][name]['runs']:
                raise ValueError('incomplete Run schedule')
            by_run[mode]=rows
            result[mode]=dict(totals=run_counts(rows),execution=x)
        with (out/(name+'.csv')).open('w') as f:
            writer=csv.writer(f,lineterminator='\n')
            writer.writerow(['run','required']+[k+'_'+m for k in by_run for m in ('recovered','issued')]
                            +['cap_lost','cap_gained','prefix_lost','prefix_gained'])
            diffs=Counter()
            for run in by_run['free']:
                base,cap,safe=[by_run[k][run] for k in by_run]
                if len({x['required'] for x in (base,cap,safe)})!=1:
                    raise ValueError('different teacher denominator')
                a,b,c=[set(x['winner_ids']) for x in (base,cap,safe)]
                delta=list(map(len,(a-b,b-a,b-c,c-b)))
                diffs.update(dict(zip(('cap_lost','cap_gained','prefix_lost','prefix_gained'),delta)))
                writer.writerow([run,base['required'],*(v for x in (base,cap,safe)
                                   for v in (x['recovered'],x.get('issued',0))),*delta])
        with (uncapped_reference/(name+'.csv')).open() as f:
            historical=list(csv.DictReader(f))
        for row in historical:
            actual=by_run['free'][row['run']]
            if any(int(row['disagreement_'+m])!=actual.get(m,0) for m in ('issued','recovered')):
                raise ValueError('unbounded layer order differs from frozen baseline')
        audit=read(source/f'{name}-fields.json')
        if audit['weights_sha256']!=weights or audit['cap']!=32 or audit['issued_by_run']!={r:x.get('issued',0) for r,x in by_run['cap'].items()}:
            raise ValueError('field audit saw a different policy frontier')
        for k,counts in audit['layers'].items():
            native=result['cap']['execution']['partial_proof_counts'][k]
            if any(native.get(x,0)!=counts.get(x,0) for x in ('scored','above_threshold','after_cap')):
                raise ValueError('field audit saw a different candidate matrix')
        result['post_score_fields']=audit['layers']
        result['winner_differences']=diffs
        summary['cases'][name]=result
    for name in ('loopfact','sum-divisors'):
        summary['anchor'][name]=read(source/f'{name}-anchor.json')
        prof={}
        for kind in ('base','new'):
            probe=read(source/f'{name}-{kind}-audit.json')
            if probe['receiver_sha256']!=build or not probe['policy']['audit'] or not probe['policy']['verify']:
                raise ValueError('missing native prefix audit')
            t=probe['result']
            partial=Counter()
            for depth,counts in t['partial_proof_counts'].items():
                if depth.startswith('partial'):
                    partial.update(counts)
            prof[kind]=dict(weights=probe['weights_sha256'],partial=partial,
                            native_audit_reads=t['native_partial_reads'],native_audit_probes=t['native_partial_probes'],
                            by_run=t['by_run'],layers=t['partial_proof_counts'])
        summary['profile'][name]=prof
    intervention=read(source/'loopfact-open.json')
    if not intervention['open_anchor_gate'] or intervention['weights_sha256']!=weights or intervention['receiver_sha256']!=build:
        raise ValueError('wrong anchor intervention')
    summary['open_anchor_gate']=intervention['result']['by_run']
    summary['run3_given_anchors']=read(source/'run3-oracle.json')['cases']['loopfact']
    for mode in ('cap','safe'):
        x=read(source/f'exclusive-{mode}.json')
        if x['receiver_sha256']!=build or x['weights_sha256']!=weights:
            raise ValueError('different exclusive model')
        groups=defaultdict(Counter)
        for name,v in x['cases'].items():
            e=v['execution']
            if e['mode']!='exclusive' or e['independent_search_calls']:
                raise ValueError('exclusive execution consulted search')
            groups[v['split']].update(programs=1,final_equal=int(v['final_equal']),required=v['reference_commits'],
                common_prefix_commits=v['committed_reference_prefix'],issued=e['issued'],accepted=e['counts']['accepted'],
                duplicates=e['counts']['duplicates'],rejected=sum(e['counts']['rejected'].values()),runs=e['runs'],
                receiver_reads=e['counts']['reads'],prefix_reads=e['native_partial_reads'],wall_seconds=e['wall_seconds'],
                network_seconds=e['network_seconds'],verifier_seconds=e['native_verify_seconds'],prefix_seconds=e['native_partial_seconds'])
            if v['split']=='eggcc':
                summary['proofs'].setdefault(name,{})[mode]=dict(common_runs=v['common_runs'],final_equal=v['final_equal'])
        summary['holdouts'][mode]=groups
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('out',type=Path)
    parser.add_argument('--uncapped-reference',required=True,type=Path)
    args=parser.parse_args()
    summarize(args.source,args.out,args.uncapped_reference)
