"""Check the provenance of each surviving child after broad or dependency-specific retirement."""
import argparse
import json
from pathlib import Path
import numpy as np
from study import inputs,load_catalog,pair_joins,read


def audit(a):
    donor=a.ref/'sum-bits/program.json';joins=pair_joins(read(donor))
    records=read(a.runs/'results.json');result={}
    for key,expected in records.items():
        case,seed,scenario=key.split('/')
        image,p,_=inputs(a.corpus,a.ref,case)
        entries=load_catalog(image,p,donor)
        with np.load(a.capture/case/'neural-inputs.npz') as z:
            pub,consumed=z['publications'],z['consumed']
        result[key]={}
        for strategy in ('batch','dependencies'):
            folder=a.runs/f'{case}-{seed}-{scenario}-{strategy}'
            with np.load(folder/'compound-output.npz') as z,np.load(folder/'neural-output.npz') as n,np.load(folder/'output.npz') as g:
                claims=z['claims'];roots=n['rhs_ordinal'][:,:2];raw=n['raw'];rhs=g['rhs'];final_meta=g['meta']
                root_status=n['verdict'][:,:2,0]
            seen=set(map(int,roots[roots>0]));checked=0
            for issue,child in zip(*np.nonzero(claims[:,:,7])):
                parent,j,o,row,ticket,release,_,winner,status,*_=map(int,claims[issue,child])
                _,left,port,right=joins[j]
                assert roots[issue,parent]==o and raw[issue,parent,8]==left+1 and o>0
                np.testing.assert_array_equal(raw[issue,child+2,-4:],[right+1,2*issue+parent+1,port+1,1])
                assert tuple(pub[ticket-1])==(o,port,row,entries[right][3])
                assert tuple(rhs[winner-1,[0,1,3]])==(release,entries[right][0],row)
                assert status==6 and release>issue+1 and consumed[winner-1]==ticket and winner not in seen
                checked+=1;seen.add(winner)
            stale_checked=orphan_checked=0
            for issue,child in zip(*np.nonzero(claims[:,:,8]==3)):
                _,j,parent,row,ticket,boundary,replacement,_,_,_,_=map(int,claims[issue,child])
                _,_,port,right=joins[j];table=entries[right][3]
                assert tuple(pub[ticket-1])==(parent,port,row,table) and boundary>issue+1
                if replacement>0:
                    replacement_parent,_,other_replacement_row,other_table=map(int,pub[replacement-1])
                    assert other_table==table and replacement!=ticket and rhs[replacement_parent-1,0]<boundary
                    if other_replacement_row==row:assert rhs[replacement_parent-1,0]+1==boundary
                else:
                    assert replacement in (-1,-2) and final_meta[row,3] in (1,2)
                    if replacement==-2:assert final_meta[row,3]==2
                stale_checked+=1
            for issue,child in zip(*np.nonzero(claims[:,:,8]==7)):
                parent=int(claims[issue,child,0])
                assert root_status[issue,parent]!=1 and not roots[issue,parent]
                orphan_checked+=1
            assert checked==expected[strategy]['children'] and len(rhs)-len(seen)==expected[strategy]['exact']
            result[key][strategy]=dict(verified_child_source_tickets=checked,verified_root_and_child_ordinals=len(seen),
                                       stale_sources_checked=stale_checked,failed_parents_checked=orphan_checked,
                                       exact_residual=len(rhs)-len(seen))
    a.out.write_text(json.dumps(result,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','capture','runs','out'):p.add_argument(k,type=Path)
    audit(p.parse_args())
