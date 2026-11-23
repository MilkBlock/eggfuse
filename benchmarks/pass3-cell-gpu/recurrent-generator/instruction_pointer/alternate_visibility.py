"""Check whether verified substitutions even change inputs to the one-batch pointer."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import torch

from alternate_proofs import addr,digest
from history import History
from rule_read import load_actor


@torch.no_grad()
def audit(root,labels,weights):
    torch.set_num_threads(1)
    actor=load_actor(weights,True)
    records=json.loads(labels.read_bytes())
    total=Counter()
    ties={}
    for name,source in records['programs'].items():
        if not source['proofs']: continue
        folder=root/name
        if digest(folder/'tape.json')!=source['teacher_sha256'] or digest(folder/'memory.jsonl')!=source['memory_sha256']:
            raise ValueError('mismatched checked prefix')
        cat=actor.catalog_type(json.loads((folder/'program.json').read_bytes()))
        nodes=actor.template_graph(cat)
        hist=History(cat,records['seed'])
        refs={p['token']:p for p in json.loads((folder/'tape.json').read_bytes())['requests']}
        matches=defaultdict(list)
        for p in source['proofs']:matches[p['run']].append(p)
        unseen=set()
        with (folder/'memory.jsonl').open() as f:
            for line in f:
                raw=json.loads(line)
                snap=hist.snapshot(raw,raw['run'] in matches)
                if snap is None: continue
                mem=actor.memory(cat,snap,nodes)
                lookup={(hist.inverse[p.address[0]],p.address[1]):i for i,p in enumerate(mem.ports)}
                for child in matches[snap.run]:
                    orig=refs[child['winner']]
                    a=[lookup[addr(x['address'])] for x in orig['parents']]
                    b=[lookup[addr(x['address'])] for x in child['parents']]
                    which,=[i for i,(x,y) in enumerate(zip(a,b,strict=True)) if x!=y]
                    x,y=a[which],b[which]
                    rid=orig['rule']
                    def anchor(js):
                        return next(i for i,j in enumerate(js) if not cat.seminaive[rid] or
                                    mem.ports[j].version>=mem.rules[rid])
                    same_owner=anchor(a)==anchor(b)
                    same_address_tests=all((x==j)==(y==j) for i,j in enumerate(a) if i!=which)
                    same_key=torch.equal(mem.keys[x],mem.keys[y])
                    same_fields=torch.equal(mem.fields[x],mem.fields[y])
                    if not same_fields:raise ValueError('row substitution changed field encoding')
                    identical=same_owner and same_address_tests and same_key
                    total.update(certified=1,same_anchor=int(same_owner),identical_key=int(same_key),
                                 indistinguishable=int(identical))
                    if identical:unseen.add(child['winner'])
        ties[name]=len(unseen)
    return dict(weights_sha256=digest(weights),labels_sha256=digest(labels),counts=total,
                commits_with_indistinguishable_substitutions=ties)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','labels','weights','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    a.out.write_text(json.dumps(audit(a.root,a.labels,a.weights),indent=2)+'\n')
