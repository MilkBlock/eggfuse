"""Jointly forbid root and nested default construction, and test invalid root recipes at first allocation."""
import argparse,json,subprocess
from pathlib import Path
from study import read,audit,joint


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','high','multi','merged','root','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);result={}
    for key,report in read(a.root/'results.json').items():
        case,seed,regime=key.split('/');program=a.ref/case/'program.json' if case in ('sum-bits','dot-product') else a.corpus/case/'program.json'
        plan=a.high/f'{case}-plans.json'
        single=a.high/f'{case}-{seed}-target.json' if regime=='high' else a.root/f'{case}-{seed}-certified.json'
        merge=read(a.merged/f'{case}-{seed}-learned.json');merge['forbid_fallback']=True;mp=a.out/f'{case}-{seed}-both.json';mp.write_text(json.dumps(merge))
        proc=subprocess.Popen([a.binary,program,plan],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);rows={}
        try:
            for control in ('use','wrong-port','wrong-template'):
                rp=a.out/f'{case}-{seed}-{regime}-{control}.json';rp.write_text(json.dumps(dict(control=control,forbid_fallback=True)))
                r=joint.rpc(proc,dict(single_config=str(single),multi_weights=str(a.multi/seed/'model.json'),cap=1000000,radius=2,
                        multi_residual=False,multi_mode='stackseal3xlearned',audit=True,merge_config=str(mp),root_config=str(rp)))
                if 'source_error' in r:
                    assert ('no verified root recipe' in r['source_error'] or 'no verified neural template' in r['source_error'])
                    rows[control]=dict(error=r['source_error'],first_uncompleted_run=r['runs']+1)
                    if control!='use':assert rows[control]['first_uncompleted_run']==1 and 'root recipe' in r['source_error']
                else:
                    assert control=='use';v=audit(r,case,a,read(plan),control)
                    assert v['direct_distinct']==report['use']['direct_distinct']
                    rows[control]=dict(source_exact=True,direct=v['direct_distinct'],fresh=v['fresh'],rhs=v['rhs'])
            result[key]=rows;(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        finally:
            proc.stdin.close();proc.wait()
            if proc.returncode:raise RuntimeError(proc.stderr.read().decode()[-2048:])
