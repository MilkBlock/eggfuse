"""Generate training-side source programs and measure both native actions at the same decision."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

DIVERSITY=('affine-twins','clamped-ramp','segmented-prefix','window-laplacian')
SYNTHETIC=('s0','s1','s2','s3')

def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def synth(index):
    extras=' '.join(f'(record{j} x)' for j in range(index))
    declarations='\n'.join(f'(relation record{j} (E))' for j in range(index))
    roots='\n'.join(f'(N {j})' for j in range(index+2))
    return f'''(datatype E (N i64) (F E) (G E) (H E) (Seen E))
(relation External (E))
{declarations}
(ruleset a)
(ruleset b)
(ruleset c)
(ruleset outside)
(ruleset idle)
(rule ((= x (N n))) ((G (F x)) {extras}) :ruleset a)
(rule ((= x (G y))) ((H x) {extras}) :ruleset b)
(rule ((= x (H y))) ((Seen x)) :ruleset c)
(rule ((= x (H y))) ((External x) (External y)) :ruleset outside)
{roots}
(run-schedule (seq (run a) (run b) (run outside) (run c) (run idle) (run idle)))
'''

def native(binary,program,mode,dest,cut,skip,weight=None,capture=False):
    subprocess.run([binary,program,mode,dest,'pooled','0',str(cut),str(skip),weight or '-', 'capture' if capture else 'full'],check=True)
    return json.loads(dest.read_bytes())

def action(run):
    events=[e for e in run['events'] if e['event']['kind']=='existing_pair']
    assert len(events)<=1
    return events[0] if events else None

def allocation(e):
    if e['allocation'] is None:return [0,0]
    before,after=e['allocation']
    return [before[0]-after[0],after[3]-before[0]]

def collect(a):
    a.out.mkdir(parents=True,exist_ok=False);rows=[]
    for i,name in enumerate((*SYNTHETIC,*DIVERSITY)):
        if name in SYNTHETIC:
            source=a.out/(name+'.egg');source.write_text(synth(i));group='synthetic'
        else:
            source=a.corpus/name/'program.json';group='workload'
        baked=a.out/name
        subprocess.run([a.baker,source,baked],check=True)
        with tempfile.TemporaryDirectory(dir=a.out) as tmp:
            out=Path(tmp)/'source.json'
            for cut,skip in [(0,0),(1,0),(0,2),(1,2)]:
                keep=native(a.engine,baked/'program.json','split-keep',out,cut,skip,capture=True)
                e=action(keep)
                row={'family':name,'group':group,'cut':cut,'skip':skip,'eligible':bool(e)}
                if e:
                    merged=native(a.engine,baked/'program.json','split-merge',out,cut,skip,capture=True)
                    m=action(merged);assert m and m['source_run']==e['source_run']
                    assert keep['final_state']==merged['final_state'] and keep['source_checks']==merged['source_checks']
                    x,y=e['event'],m['event']
                    assert x['old']==x['new']==y['old']==y['new'] and x['old_members']==y['old_members']
                    assert x['issuer']['features']==y['issuer']['features'] and y['outcome']['merged']==1
                    reward,peak=allocation(y)
                    row.update(x=y['issuer']['features'],saved_bytes=reward,peak_bytes=peak,source_digest=sha(merged['source_checks']),source_run=m['source_run'])
                rows.append(row)
            print(name,[(r.get('x'),r.get('saved_bytes')) for r in rows[-4:]],flush=True)
            (a.out/'train.json').write_text(json.dumps(rows,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('engine','baker','corpus','out'):p.add_argument(k,type=Path)
    collect(p.parse_args())
