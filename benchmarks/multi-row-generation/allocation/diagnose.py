"""Post-hoc error decomposition; never used to repair or select model outputs."""
import argparse,json
from collections import Counter
from pathlib import Path
import numpy as np
from data import truth


def inspect(path):
    counts=Counter();examples=[]
    with np.load(path,allow_pickle=False) as z:
        for g,(a,b) in enumerate(zip(z['a'],z['b'])):
            expected={(i,j):(k,x,y) for i,j,k,x,y in truth(a,b)};pred=[];wrong_fields=0;illegal=0
            for s in np.flatnonzero(z['active'][g]):
                pair=tuple(map(int,z['pointers'][g,s]));pred.append(pair)
                if pair not in expected:illegal+=1
                else:wrong_fields+=tuple(z['fields'][g,s])!=expected[pair]
            valid=[p for p in pred if p in expected];missing=len(set(expected)-set(valid));duplicate=len(valid)-len(set(valid))
            counts['graphs']+=1;counts['missing_bindings']+=missing;counts['duplicate_legal_bindings']+=duplicate
            counts['illegal_bindings']+=illegal;counts['wrong_fields_on_legal_bindings']+=wrong_fields
            counts['binding_set_exact_graphs']+=not(missing or duplicate or illegal)
            counts['coverage_only_failure_graphs']+=bool(missing or duplicate) and not(illegal or wrong_fields)
            counts['field_only_failure_graphs']+=bool(wrong_fields) and not(missing or duplicate or illegal)
            counts['illegal_binding_graphs']+=bool(illegal)
            counts['wrong_fields_graphs']+=bool(wrong_fields)
            if bool(missing or duplicate) and not(illegal or wrong_fields) and len(examples)<2:
                examples.append(dict(a=a.tolist(),b=b.tolist(),expected=[list(p) for p in expected],predicted=[list(p) for p in pred],missing=missing,duplicates=duplicate))
    return dict(counts={k:int(v) for k,v in counts.items()},coverage_examples=examples)


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result={str(path.relative_to(a.root)):inspect(path) for path in sorted(a.root.glob('*/*.npz'))}
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    for k,v in result.items():print(k,v['counts'])

if __name__=='__main__':main()
