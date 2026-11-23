"""Compare actual live assist, ordinary native search, and signed teacher replay."""
import argparse
import json
from pathlib import Path
import subprocess
from time import perf_counter

import torch

from alternate_proofs import digest
from online import execute
from prefix_policy import Policy
from rule_read import load_actor


def read(path):
    return json.loads(path.read_bytes())


def measure(folder, binary, weight, seed, arm, audit, project_ports=False):
    program = folder/'program.json'
    start = perf_counter()
    if arm == 'assist':
        actor = load_actor(weight, True)
        result = execute(binary, program, actor, seed, prefix_policy=Policy(32), assist=True, audit=audit, project_ports=project_ports)
        elapsed = perf_counter()-start
        checks = dict(schedule=result['source_schedule'],rhs=result['rhs_by_run'],writes=result['writes_by_run'],
                      resumes=result['resume_audit'],events=result['event_audit'],state_sha=result['state_sha'])
        stats = result['assist']
        counts = result['counts']
        row = dict(inference=result['network_seconds'],verify=result['native_verify_seconds'],exact=stats['exact_seconds'],
                   **stats, issued=result['issued'],accepted=counts['accepted'],duplicates=counts['duplicates'],
                   rejected=counts['rejected'],reads=counts['reads'],runs=result['runs'],waves=result['neural_waves'])
    else:
        role = 'reference' if arm == 'exact' else 'replay'
        report = json.loads(subprocess.check_output([binary,role,program,folder/'tape.json','audit' if audit else 'time']))
        elapsed = perf_counter()-start
        checks = {k:report.get(k) for k in ('schedule','rhs','writes','resumes','events','state_sha')}
        row = dict(inference=0,verify=report.get('verify_seconds',0),
                   exact=report['source_search_phase_seconds'] if arm=='exact' else 0,
                   runs=report['runs'], committed=report['matches'], phase_search=report['source_search_phase_seconds'],
                   residual_candidates=report['residual_candidates'],counts=report.get('counts'))
    ref = read(folder/'capture.json')
    for k in (checks if audit else ('schedule','state_sha')):
        if checks[k] != ref[k]:
            raise ValueError(f'{folder.name} {arm} differs from native reference in {k}')
    return dict(arm=arm,wall=elapsed,**row,state_sha=checks['state_sha'])


def main(root,binary,weights,out,names,repeats,project_ports=False):
    torch.set_num_threads(1)
    manifest = {r['directory']:r for r in read(root/'manifest.json')}
    out.mkdir(parents=True,exist_ok=True)
    for name in names:
        seed=1703+manifest.get(name,{}).get('seed',0)
        path=out/(name+'.json')
        spec=dict(program=digest(root/name/'program.json'),binary=digest(binary),weights=digest(weights),seed=seed)
        if project_ports:
            spec['project_ports'] = True
        report=read(path) if path.exists() else dict(spec=spec, audit={},pairs=[])
        if report['spec']!=spec:raise ValueError('changed timing inputs')
        def save():
            temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps(report,indent=2)+'\n')
            temp.replace(path)
        for arm in ('exact','oracle','assist'):
            if arm not in report['audit']:
                report['audit'][arm]=measure(root/name,binary,weights,seed,arm,True,project_ports)
                save()
        for i in range(len(report['pairs']),repeats):
            order = ('exact','assist','oracle') if i%2==0 else ('oracle','assist','exact')
            trial=[measure(root/name,binary,weights,seed,a,False,project_ports) for a in order]
            report['pairs'].append(trial)
            save()
            print(name, i+1,[(r['arm'],round(r['wall'],3)) for r in trial],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','binary','weights','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    p.add_argument('--repeats',type=int,default=4)
    p.add_argument('--project-ports', action='store_true')
    a=p.parse_args()
    main(a.root,a.binary,a.weights,a.out,a.cases,a.repeats,a.project_ports)
