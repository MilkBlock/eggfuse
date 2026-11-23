"""Replay counterfactual thresholds on the policy's actual first incomplete source snapshot."""
from collections import defaultdict
from pathlib import Path
import argparse
import json
import torch

from alternate_proofs import digest
from first_boundary import receipt_probe
from online import execute
from prefix_policy import Policy,generate
from rule_read import load_actor


@torch.no_grad()
def case(folder,binary,weights,diagnosis,seed):
    model=load_actor(weights,True)
    tape=json.loads((folder/'tape.json').read_bytes())
    run=diagnosis['first']
    prior=defaultdict(list)
    trials={}
    def record(packets):
        for p in packets:
            prior[p['run']].append(p)
    def snapshot(cat,h,s):
        if s.run!=run:return
        mem=model.memory(cat,s)
        saved=model.thresholds.clone()
        try:
            for name,k,roots,parents in [('actual',32,False,False),('larger_cap',128,False,False),
                                         ('open_root',32,True,False),('open_parents',32,False,True),
                                         ('both_open',32,True,True)]:
                model.thresholds.copy_(saved)
                if roots:model.thresholds[1]=-torch.inf
                if parents:model.thresholds[2]=-torch.inf
                packets=[]
                for rid,refs in generate(model,cat,mem,Policy(k)):
                    pp=[]
                    for alias,op in refs:
                        token=h.inverse[alias]
                        pp.append(dict(address=dict(token=token,op=op),version=h.visible[token,op]['version']))
                    packets.append(dict(run=run,rule=rid,token=len(packets)+1,parents=pp))
                trials[name]=packets
        finally:
            model.thresholds.copy_(saved)
    execute(binary,folder/'program.json',model,seed,prefix_policy=Policy(32),observe_packets=record,
            observe_snapshot=snapshot,run_limit=run)
    def signature(items):return [(p['rule'],p['parents']) for p in items]
    if signature(trials['actual'])!=signature(prior[run]):
        raise ValueError('counterfactual ingress changed the actual proposal stream')
    known={}
    for r in range(1,run):
        hits,ledger=receipt_probe(folder,binary,tape,prior[r],known,r)
        if ledger['distinct']!=diagnosis['runs'][str(r)]['required'] or ledger['unresolved']:
            raise ValueError('incomplete predecessor correspondence')
        known.update(hits)
    required={p['token'] for p in tape['requests'] if p['run']==run}
    out={}
    for name,packets in trials.items():
        hits,ledger=receipt_probe(folder,binary,tape,packets,known,run)
        ledger['missing']=sorted(required-set(hits.values()))
        out[name]=ledger
    if out['actual']['missing']!=diagnosis['runs'][str(run)]['missing_winners']:
        raise ValueError('bad-boundary replay differs')
    return dict(run=run,required=len(required),trials=out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','binary','weights','boundaries','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    torch.set_num_threads(1)
    raw=json.loads(a.boundaries.read_bytes())
    if raw['receiver_sha256']!=digest(a.binary) or raw['weights_sha256']!=digest(a.weights):
        raise ValueError('different native policy')
    seeds={r['directory']:r['seed'] for r in json.loads((a.root/'manifest.json').read_bytes())}
    result={n:case(a.root/n,a.binary,a.weights,v,1703+seeds.get(n,0)) for n,v in raw['cases'].items()}
    a.out.write_text(json.dumps(dict(receiver_sha256=digest(a.binary),weights_sha256=digest(a.weights),
                                     cases=result),indent=2)+'\n')
