"""Exercise exclusive wave transport with the frozen, receipt-blind sequence policy."""
import argparse
import json
from pathlib import Path
from collections import defaultdict
import subprocess

import torch

from online import execute
from rule_read import load_actor


def teacher_parity(folder,receiver):
    tape = json.loads((folder/'tape.json').read_bytes())
    native = json.loads((folder/'capture.json').read_bytes())
    by_run = defaultdict(list)
    for packet in tape['requests']:
        by_run[packet['run']].append(packet)
    cmd = [receiver,'online-waves',folder/'program.json','-','audit']
    with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) as child:
        try:
            for line in child.stdout:
                frame=json.loads(line)
                if 'role' in frame:
                    report=frame
                    break
                packets=by_run[frame['run']]
                for start in range(0,len(packets),4):
                    wave=packets[start:start+4]
                    child.stdin.write(json.dumps(dict(finish=False,requests=wave))+'\n')
                    child.stdin.flush()
                    reply=json.loads(child.stdout.readline())
                    if reply!={'run':frame['run'],'verdicts':[[p['token'],'accepted'] for p in wave]}:
                        raise ValueError('valid teacher wave was not fully admitted')
                child.stdin.write('{"finish":true,"requests":[]}\n')
                child.stdin.flush()
        finally:
            child.stdin.close()
            if 'report' not in locals(): child.kill()
        if child.wait() or report['unused'] or report['wave_requests']!=native['matches']:
            raise ValueError('incomplete streaming teacher')
    if any(report[k]!=native[k] for k in ('schedule','rhs','writes','state_sha','events','resumes')):
        raise ValueError('streaming teacher changed a native Run')
    return dict(commits=native['matches'],runs=native['runs'],batches=report['wave_batches'],
                repair_events=len(report['runtime_events']),state_sha=report['state_sha'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','receiver','weights','output'):
        p.add_argument(name,type=Path)
    p.add_argument('--workloads',nargs='+',required=True)
    p.add_argument('--teacher',action='store_true')
    args=p.parse_args()
    torch.set_num_threads(1)
    model=load_actor(args.weights,True)
    if getattr(model,'requires_receipts',False):
        raise ValueError('parity requires a receipt-blind checkpoint')
    cases={}
    keys=('counts','source_schedule','writes_by_run','rhs_by_run','state_sha','wave_endings','issued','native_runtime_events')
    for name in args.workloads:
        if args.teacher:
            cases[name]=teacher_parity(args.root/name,args.receiver)
            continue
        program=args.root/name/'program.json'
        old=execute(args.receiver,program,model,1703,live_receipts=False)
        new=execute(args.receiver,program,model,1703,live_receipts=True)
        if any(old[k]!=new[k] for k in keys):
            raise ValueError(f'wave transport changed {name}')
        cases[name]=dict(equal=keys,counts=new['counts'],batches=new['receipt_batches'],state_sha=new['state_sha'])
    args.output.write_text(json.dumps(cases,indent=2)+'\n')
