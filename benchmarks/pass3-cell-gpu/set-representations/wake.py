"""Diagnostic native displaced-port records validate row notifications, including set-only readers."""
import argparse,json,subprocess,os
from pathlib import Path


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    base=json.loads((a.study/'results.json').read_bytes())
    for case,info in base.items():
        if case=='no-merge':continue
        program=(a.fixtures if info['stress'] else a.sources)/case/'program.json'
        report={};expected=None
        for k,v in info['arms'].items():
            if v['status']!='accepted':continue
            typ,subs=k.split('-');dest=a.out/f'{case}-{k}'
            proc=subprocess.run([a.runtime,'--program',program,'--output',dest,'--audit-repair-inputs'],
                     env=dict(os.environ,EGGFUSE_SET_REPR=typ,EGGFUSE_SET_SUBSCRIPTION=subs,EGGFUSE_SET_WAKE_AUDIT='1'),
                     stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            if proc.returncode:raise RuntimeError(proc.stderr.decode())
            sets=json.loads((dest/'report.json').read_bytes())['set_storage']
            rows=sets['observed_set_rows_woken'] if subs=='row' else sets['notified_rows']
            if expected is None:expected=rows
            assert expected==rows,(case,k,expected,rows)
            events=json.loads((dest/'events.json').read_bytes())
            decreases=[(x[4],x[5],x[6],x[7]) for stream in events for x in stream if x[0]=='write' and x[6]=={'Int':2} and x[7]=={'Int':1}]
            if case=='dynamic':assert len(decreases)==1
            report[k]=dict(actual_set_rows_woken=rows,actual_set_groups_woken=sets['notified_groups'] if subs=='instance' else None,
                           same_key_two_to_one=len(decreases),union_events=sum(x[0]=='union' for stream in events for x in stream))
        results[case]=report
        (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,expected,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('runtime','sources','fixtures','study','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
