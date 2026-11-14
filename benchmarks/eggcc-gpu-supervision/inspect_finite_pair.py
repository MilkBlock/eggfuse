"""Trace near-identical readout states back to their actual transition inputs."""
import argparse,json
from pathlib import Path
import numpy as np
from device_stage_models import select_ruleset
from finite_entry_domain import input_cases
from neural_cell_samples import samples
from neural_cell_chains import chains


def difference(a,b):
    return dict(shape=list(a.shape),different_elements=int(np.sum(a!=b)),
                max_abs=float(np.max(np.abs(a.astype(np.float64)-b.astype(np.float64)))))


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--pair',nargs=2,type=int,required=True);p.add_argument('--capture',type=Path);a=p.parse_args()
    raw=json.loads(a.trace.read_text());recipe,_=select_ruleset(raw.get('recipe',raw),'canon');records=[]
    base=samples(recipe,1,0,records,ordered=True,eq_targets=True,input_cases={i:input_cases(r) for i,r in enumerate(recipe['rules'])})
    data,_=chains(recipe,records,ordered=True,eq_targets=True,finite_boundary=True)
    pos=np.flatnonzero(data['valid']);i,j=(int(pos[k]) for k in a.pair);pi,pj=int(data['parent'][i]),int(data['parent'][j])
    inputs={}
    for key in ('x','edges','mask','request','relations'):inputs['parent_'+key]=difference(base[key][pi],base[key][pj])
    for key in ('seed_x','edges','mask','replace','request','relations'):inputs[key]=difference(data[key][i],data[key][j])
    width=max(len(r['slots']) for r in recipe['rules']);pairs=list(zip(*np.triu_indices(width,1)))
    bad=np.flatnonzero((data['eq_target'][i]!=data['eq_target'][j])&data['eq_mask'][i]&data['eq_mask'][j])
    result=dict(scope='finite synthetic transition input diagnostic, not learned-output equivalence proof',positive_indices=a.pair,
        producers=[int(data['producer'][k]) for k in (i,j)],consumers=[int(data['consumer'][k]) for k in (i,j)],
        parent_indices=[pi,pj],inputs=inputs,
        differing_labels=[dict(slots=[int(x) for x in pairs[k]],left=float(data['eq_target'][i,k]),right=float(data['eq_target'][j,k])) for k in bad])
    if a.capture:
        np.savez_compressed(a.capture,**{'p_'+k:v[[pi,pj]] for k,v in base.items()},**{'c_'+k:v[[i,j]] for k,v in data.items()})
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
