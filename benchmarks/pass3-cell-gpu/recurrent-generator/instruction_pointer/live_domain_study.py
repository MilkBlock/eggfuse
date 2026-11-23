"""Run the frozen Actor against a live assistant and retain its complete named stream."""
import argparse
import json
from pathlib import Path
from time import perf_counter

import torch
from alternate_proofs import digest
from online import execute
from prefix_policy import Policy
from rule_read import load_actor


def measure(folder, binary, weights, seed, projected, output, stream):
    actor = load_actor(weights,True)
    packets=[]
    start=perf_counter()
    r=execute(binary,folder/'program.json',actor,seed,assist=True,prefix_policy=Policy(32),
              observe_packets=packets.extend,project_ports=projected)
    wall=perf_counter()-start
    c=json.loads((folder/'capture.json').read_bytes())
    for key,target in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes'),
                       ('event_audit','events'),('resume_audit','resumes'),('state_sha','state_sha')]:
        if r[key]!=c[target]:
            raise ValueError('live assist drift in '+key)
    stream.write_text(json.dumps(packets))
    for key in ('source_schedule','rhs_by_run','writes_by_run','event_audit','resume_audit','partial_proof_counts'):
        del r[key]
    output.write_text(json.dumps(dict(receiver=digest(binary),actor=digest(weights),program=digest(folder/'program.json'),
        projected=projected,stream=digest(stream),wall=wall,result=r),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','case','binary','weights','output','stream'):
        p.add_argument(n,type=str if n=='case' else Path)
    p.add_argument('--project',action='store_true')
    a=p.parse_args()
    torch.set_num_threads(1)
    seeds={r['directory']:r['seed'] for r in json.loads((a.root/'manifest.json').read_bytes())}
    measure(a.root/a.case,a.binary,a.weights,1703+seeds.get(a.case,0),a.project,a.output,a.stream)
