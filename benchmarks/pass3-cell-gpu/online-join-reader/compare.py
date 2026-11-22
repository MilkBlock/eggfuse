"""Audit autonomous trajectory against a separate native exact execution."""
import argparse
import json
from pathlib import Path
import subprocess


def compare(data,ref):
    keys=('rhs','writes','state_sha','resumes','events','schedule')
    checks={k:data[k]==ref[k] for k in keys}
    def mutations(events):
        return [[e for e in rows if e[0]!='resume'] for rows in events]
    checks['mutation_trace']=mutations(data['events'])==mutations(ref['events'])
    n=0
    for observed,expected,os,es in zip(data['rhs'],ref['rhs'],data['schedule'],ref['schedule']):
        if observed!=expected or os!=es:
            break
        n+=1
    return dict(checks=checks,aligned_prefix=n,runs=len(data['schedule']),source_runs=len(ref['schedule']),
                first_observed=data['schedule'][n:n+1],first_expected=ref['schedule'][n:n+1],
                observed_rhs=sum(s[4] for s in data['schedule']),source_rhs=sum(s[4] for s in ref['schedule']),
                **{k:data[k] for k in ('issuer','accepted','rejected','named_reads','failure')})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('reference','bundle','trajectory','out'):
        p.add_argument(k,type=Path)
    p.add_argument('--plans',type=Path,help='opaque plans file required by the independent exact-session CLI')
    a=p.parse_args()
    ref=json.loads(subprocess.check_output([a.reference,a.bundle/'program.json',a.plans or a.bundle/'plans.json'],
                   input='{"baseline":true,"audit":true}\n',text=True))
    result=compare(json.loads(a.trajectory.read_bytes()),ref)
    print(json.dumps(result,indent=2))
    a.out.write_text(json.dumps(result,indent=2)+'\n')
