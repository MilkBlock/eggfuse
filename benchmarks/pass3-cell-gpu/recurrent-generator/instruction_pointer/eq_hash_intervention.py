"""Change only the coordinate signs of opaque e-class hashes on a sealed snapshot."""
import argparse
from collections import Counter,defaultdict
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random

import torch
from alternate_proofs import digest
from anchor_set_audit import check
from history import History
from prefix_policy import Policy, generate
from rule_read import load_actor


from typed_content import Schemas


class CoordinateChange(Schemas):
    @staticmethod
    def change(values,schema,salt):
        return tuple(h^salt if opaque else h for h,opaque in zip(values,schema,strict=True))

    def transform(self,snap,salt):
        ports=[]
        for p in snap.ports:
            inputs=tuple((role,replace(parent,hashes=self.change(parent.hashes,self.inputs[p.root,role],salt)))
                         for role,parent in p.inputs)
            ports.append(replace(p,hashes=self.change(p.hashes,self.rows[p.table],salt),inputs=inputs))
        return replace(snap,ports=ports)


@torch.no_grad()
def inspect(folder,binary,model,runs,salts,seed):
    program=json.loads((folder/'program.json').read_bytes())
    tape=json.loads((folder/'tape.json').read_bytes())
    required=Counter(r['run'] for r in tape['requests'])
    cat=model.catalog_type(program)
    schemas=CoordinateChange(cat,program)
    nodes=model.template_graph(cat)
    history=History(cat,seed)
    packets=[]
    which=[]
    records={r:{} for r in runs}
    with (folder/'memory.jsonl').open() as f:
        for line in f:
            snap=history.snapshot(json.loads(line))
            if snap.run not in runs:
                continue
            for j,salt in enumerate(salts):
                view=schemas.transform(snap,salt)
                mem=model.memory(cat,view,nodes)
                proof=[]
                for rid,refs in generate(model,cat,mem,Policy(32)):
                    parents=[]
                    for alias,op in refs:
                        tok=history.inverse[alias]
                        parents.append(dict(address=dict(token=tok,op=op),version=history.visible[tok,op]['version']))
                    packets.append(dict(run=snap.run,rule=rid,parents=parents,token=len(packets)+1))
                    which.append(j)
                    proof.append((rid,tuple((p['address']['token'],p['address']['op'],p['version']) for p in parents)))
                records[snap.run][j]=dict(issued=len(proof),required=required[snap.run],
                    proof_set_sha256=hashlib.sha256(json.dumps(sorted(proof)).encode()).hexdigest(),hits=set())
            if snap.run==max(runs):
                break
    checked=check(folder,binary,tape,packets)
    for run,t,w,reason in checked['recall_verdicts']:
        row=records[run][which[t-1]]
        if w is not None:row['hits'].add(w)
    for arms in records.values():
        base=arms[0]['hits']
        for r in arms.values():
            hits=r.pop('hits')
            r.update(recovered=len(hits),lost=len(base-hits),gained=len(hits-base),
                     changed_proofs=r['proof_set_sha256']!=arms[0]['proof_set_sha256'])
    return records


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','binary','weights','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    p.add_argument('--runs',nargs='+',type=int,required=True)
    a=p.parse_args()
    torch.set_num_threads(1)
    model=load_actor(a.weights,True)
    rng=random.Random(1703)
    salts=[0]+[rng.getrandbits(64) for _ in range(3)]
    seeds={r['directory']:r['seed'] for r in json.loads((a.root/'manifest.json').read_bytes())}
    cases={n:inspect(a.root/n,a.binary,model,set(a.runs),salts,1703+seeds.get(n,0)) for n in a.cases}
    a.out.write_text(json.dumps(dict(weights_sha256=digest(a.weights),receiver_sha256=digest(a.binary),
                                    masks=salts,mode='same-snapshot coordinate intervention',cases=cases),indent=2)+'\n')
