"""Census real Pass 3 and intervene on two already-allocated native owners at a settled Run boundary."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

def read(f):return json.loads(f.read_bytes())
def digest(v):return sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def test(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    for name in a.cases:
        program=a.corpus/name/'program.json'
        if not program.exists():program=a.corpus.parent/'pass3-atlas-integration-20261120'/name/'program.json'
        if a.catalogs:program=a.catalogs/name/'program.json'
        data=a.corpus/name/'observation'
        if name=='fixture':
            baseline=a.out/'fixture-independent.json'
            subprocess.run([a.engine,a.catalogs/name/'original.json','census',baseline,'pooled'],check=True)
            native_reference=read(baseline)
            oracle=None
        else:
            oracle={k:read(data/(k+'.json')) for k in ('state','rhs','writes','resumes','report','events')}
        records={}
        arms=[('census','pooled'),('census','unpooled'),('merge','pooled'),('split-keep','pooled'),('split-merge','pooled'),
              ('split-stale','pooled'),('split-partial','pooled'),('split-keep-probe','pooled'),('split-merge-probe','pooled')]
        if a.census_only:arms=arms[:2]
        for action,storage in arms:
            label=action+'-'+storage;dest=a.out/f'{name}-{label}.json'
            attempts=[]
            for idx in range(16):
                subprocess.run([a.engine,program,action,dest,storage,str(idx)],check=True)
                v=read(dest)
                if not action.endswith('-probe') or v['probe'] is None:break
                effect=v['probe']['effect']
                attempts.append(effect)
                if 'rejected_by_source' not in effect:break
            observed=v['source_checks']
            full=v['probe'] is None
            if oracle is None:
                assert observed==native_reference['source_checks'][:len(observed)]
                if full:assert v['final_state']==native_reference['final_state'] and len(observed)==len(native_reference['source_checks'])
            elif full:
                assert len(observed)==len(oracle['rhs'])
                assert v['final_state']==oracle['state']
            for i,stage in enumerate(observed if oracle else []):
                step=oracle['report']['steps'][i]
                assert stage[:6]==[step[k] for k in ('ruleset','path','iterations','epoch','executed_bindings','changed')]
                assert all(stage[6+j]==[oracle[k][i]] for j,k in enumerate(('rhs','writes','resumes')))
                assert stage[9]==[e for e in oracle['events'][i] if e[0]=='union']
            r={k:v[k] for k in ('domain','events','post_action_unions','probe','graph','runs')}
            r['controlled_union_attempts']=attempts
            r['source_check_digest']=digest(observed)
            r['natural_candidate_runs']=sum(q[6]>0 for q in v['per_run'])
            r['read_digest']=digest(v['post_action_read_digests'])
            r['following_reads']=len(v['post_action_read_digests'])
            records[label]=r
            trace=[(t['source_run'],t['event']['kind']) for t in r['events']]
            print(name,label,r['domain'],trace,flush=True)
            report[name]=records;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        if a.census_only:continue
        for action in ('split-merge','split-stale','split-partial'):
            cut=records[action+'-pooled'];keep=records['split-keep-pooled']
            assert cut['read_digest']==keep['read_digest'] and cut['source_check_digest']==keep['source_check_digest']
        assert records['split-merge-probe-pooled']['probe']==records['split-keep-probe-pooled']['probe']
        assert records['split-merge-probe-pooled']['controlled_union_attempts']==records['split-keep-probe-pooled']['controlled_union_attempts']
    if a.census_only:return
    assert any(any(row['event']['kind']=='existing_pair' and row['event']['outcome'].get('merged')==1
                   for row in modes['split-merge-pooled']['events']) for modes in report.values()),'no actual existing pair merged'
    assert any((modes['split-merge-probe-pooled']['probe'] or {}).get('effect',{}).get('union_delta',0)>0 for modes in report.values()),'no controlled post-transfer union ran'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('engine','corpus','out'):p.add_argument(f,type=Path)
    p.add_argument('--catalogs',type=Path)
    p.add_argument('--census-only',action='store_true')
    p.add_argument('--cases',nargs='+',default=['dot-product','stable-argmax'])
    test(p.parse_args())
