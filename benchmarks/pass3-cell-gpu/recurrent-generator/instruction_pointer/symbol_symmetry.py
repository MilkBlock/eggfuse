"""Count exact ties between distinct table declaration embeddings after the trained GNN."""
from collections import Counter
import argparse
import json
from pathlib import Path

import torch

from rule_read import load_actor
from semantic_catalog import SemanticCatalog
from symbol_audit import renamed_program


@torch.no_grad()
def count(actor,program):
    cat=SemanticCatalog(program)
    nodes=actor.template_graph(cat)
    named=nodes[[cat.roots['initial',tid] for tid in cat.tables.values()]].contiguous()
    blocks=Counter(row.tobytes() for row in named.numpy())
    return nodes,dict(tables=len(named),distinct_vectors=len(blocks),
                      tied_tables=sum(n for n in blocks.values() if n>1),
                      largest_group=max(blocks.values(),default=0))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','weights','output'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args()
    actor=load_actor(a.weights,True)
    torch.set_num_threads(1)
    report={}
    for case in a.cases:
        program=json.loads((a.root/case/'program.json').read_bytes())
        original,stats=count(actor,program)
        renamed,_=count(actor,renamed_program(program,993))
        stats['changed_nodes_on_rename']=int((original!=renamed).any(1).sum())
        if actor.name_mode=='structural' and stats['changed_nodes_on_rename']:
            raise ValueError('structural GNN depends on user names')
        report[case]=stats
    a.output.write_text(json.dumps(report,indent=2)+'\n')
