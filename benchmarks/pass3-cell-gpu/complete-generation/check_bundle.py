"""Exercise the normal offline compiler and one-shot --bundle entry without benchmark-only request fields."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
GPU=HERE.parent

def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    src=a.exp/'pass3-atlas-integration-20261120';bundle=a.out/'compiled'
    subprocess.run([sys.executable,GPU/'joint-witness/prepare.py',src/'sum-bits/program.json',src/'release-input-sum-bits',bundle,'--policy','certified','--seed','1703'],check=True)
    request=bundle/'request.json';default=json.loads(request.read_bytes());assert default['multi_generation']=='complete'
    source=json.loads(subprocess.run([a.exp/'compact-vanilla-20261121/vanilla',bundle/'program.json'],input='{}\n',text=True,capture_output=True,check=True).stdout)
    report={}
    for label,mode in [('complete','complete'),('bounded_ok','bounded'),('bounded','bounded'),('old',None),('invalid','typo')]:
        cfg=dict(default,cap=1000000 if label=='bounded_ok' else 2)
        if mode is None:cfg.pop('multi_generation')
        else:cfg['multi_generation']=mode
        request.write_text(json.dumps(cfg)+'\n')
        p=subprocess.run([a.native,'--bundle',bundle],text=True,capture_output=True)
        if label=='invalid':
            assert p.returncode and 'unknown multi-parent generation mode' in p.stderr and not p.stdout
            report[label]=dict(rejected=True)
        else:
            got=json.loads(p.stdout)
            if label in ('complete','bounded_ok'):
                assert p.returncode==0 and got['state_sha']==source['state_sha'] and got['neural_rhs']==got['rhs']==source['rhs_count']
                report[label]={k:got[k] for k in ('rhs','neural_rhs','state_sha','runs','root_recipes_applied')}
            else:
                assert p.returncode and 'incomplete multi-parent generation' in got['source_error'] and 'state_sha' not in got
                pending=got['unfinished_generation']
                assert pending['limit']==pending['attempts']==2 and pending['reason']=='unexplored_parent_branch'
                assert pending['run']==got['runs']+1
                report[label]=got
    if a.prior:
        request.write_text(json.dumps(dict(default,cap=1000000))+'\n')
        without=json.loads(subprocess.run([a.prior,'--bundle',bundle],text=True,capture_output=True,check=True).stdout)
        request.write_text(json.dumps(dict(default,cap=1000000,archive_single_winners=True))+'\n')
        with_log=json.loads(subprocess.run([a.prior,'--bundle',bundle],text=True,capture_output=True,check=True).stdout)
        assert without['state_sha']==with_log['state_sha']==source['state_sha'] and without['rhs']==with_log['rhs']==source['rhs_count']
        assert without['neural_rhs']<with_log['neural_rhs']==report['complete']['neural_rhs']
        report['old_archive_control']=dict(archive_off=without['neural_rhs'],archive_on=with_log['neural_rhs'],rhs=without['rhs'],same_state=True)
    request.write_text(json.dumps(default)+'\n')
    (a.out/'contract.json').write_text(json.dumps(report,indent=1)+'\n')
    print(report,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--prior',type=Path);run(p.parse_args())
