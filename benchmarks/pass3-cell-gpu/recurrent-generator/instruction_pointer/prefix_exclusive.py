"""Exercise capped issuance on the generator's own native trajectory, without a search fallback."""
import argparse
import json
from pathlib import Path
import subprocess

import torch

from alternate_proofs import digest
from online import execute
from prefix_policy import Policy
from rule_read import load_actor


def audit(root,binary,weights,policy):
    manifest=json.loads((root/'manifest.json').read_bytes())
    cases={r['directory']:(r['split'],r['seed']) for r in manifest
           if r['split'] in ('held_program','held_merge','held_result_pc')}
    seeds={r['directory']:r['seed'] for r in manifest}
    cases.update({n:('eggcc',seeds.get(n,0)) for n in ('fact','loopfact','sum-divisors')})
    model=load_actor(weights,True)
    results={}
    for name,(split,seed) in cases.items():
        folder=root/name
        capture=folder/'capture.json'
        ref=json.loads(capture.read_bytes()) if capture.exists() else json.loads(
            subprocess.check_output([binary,'reference',folder/'program.json','-','audit']))
        actual=execute(binary,folder/'program.json',model,1703+seed,prefix_policy=policy)
        common=0
        for i,step in enumerate(actual.pop('source_schedule')):
            if (i>=len(ref['schedule']) or step!=ref['schedule'][i]
                    or actual['writes_by_run'][i]!=ref['writes'][i] or actual['rhs_by_run'][i]!=ref['rhs'][i]):
                break
            common+=1
        del actual['writes_by_run'],actual['rhs_by_run']
        results[name]=dict(split=split,final_equal=actual['state_sha']==ref['state_sha'],common_runs=common,
                           reference_runs=ref['runs'],reference_commits=ref['matches'],reference_seconds=ref['seconds'],
                           committed_reference_prefix=sum(step[4] for step in ref['schedule'][:common]),execution=actual)
    return dict(policy=vars(policy),weights_sha256=digest(weights),receiver_sha256=digest(binary),cases=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','binary','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--top-k',type=int,required=True)
    p.add_argument('--verify-prefix',action='store_true')
    args=p.parse_args()
    torch.set_num_threads(1)
    out=audit(args.root,args.binary,args.weights,Policy(args.top_k,args.verify_prefix))
    args.out.write_text(json.dumps(out,indent=2)+'\n')
