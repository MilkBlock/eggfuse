"""One independent device check of the three envelope encodings; native CPU is the primary timing study."""
import argparse
from pathlib import Path
import json,sys
import numpy as np
from execute import config,executor,GPU
sys.path.insert(0,str(GPU/'recurrent-generator'))
from catalog import load_catalog,read
from capture import inputs,verify


def control(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    for case in a.cases:
        image,p,gold=inputs(a.corpus,a.ref,case);donor=a.ref/'sum-bits/program.json'
        cat=load_catalog(image,p,donor);schema=read(image/'ingress.json')
        model=read(a.model/'train-1703/model.json');cfg=config(model,cat,True);baseline=None
        records={}
        for kind in ('raw','leaf','macro'):
            dest=a.out/f'{case}-{kind}'
            executor(kind)(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,neural=cfg,count_work=True)
            verify(dest,gold,image)
            with np.load(dest/'issued.npz') as u,np.load(dest/'neural-output.npz') as z,np.load(dest/'compound-output.npz') as c,np.load(dest/'output.npz') as g:
                headers=u['headers'];raw=z['raw'];root=z['rhs_ordinal'];claims=c['claims'];rhs=g['rhs']
                assert raw.shape[1]==2 and root.shape==raw.shape[:2] and headers.shape[:2]==root.shape
                if baseline is None:baseline=raw.copy()
                else:np.testing.assert_array_equal(raw,baseline)
                active=int((headers[:,:,0]>=0).sum());root_ids=root[root>0];child_ids=claims[:,:,7][claims[:,:,7]>0]
                assert len(set(map(int,np.r_[root_ids,child_ids])))==len(root_ids)+len(child_ids)
                for t,row in zip(*np.where(root>0)):
                    ordinal=root[t,row];leaf=int(raw[t,row,-4])-1;rid,pivot,_,_=cat[leaf]
                    assert (rhs[ordinal-1,[0,1,3]]==[t+1,rid,headers[t,row,1]]).all()
                    if kind=='raw':
                        assert headers[t,row,0]==rid and u['raw'][t,row,0]==pivot
                        width=len(schema['rules'][rid]['inputs'])
                        np.testing.assert_array_equal(rhs[ordinal-1,4:4+width],u['raw'][t,row,2:2+width])
                for t,row in zip(*np.where(claims[:,:,7]>0)):
                    parent,j,parent_rhs,physical,ticket,later,_,child,*_=claims[t,row]
                    unit,left,effect,right=model['joins'][j]
                    assert kind=='macro' and headers[t,row,0]==unit and parent==row and parent_rhs==root[t,row]>0
                    assert later>t+1 and ticket>0 and rhs[child-1,1]==cat[right][0] and rhs[child-1,3]==physical
                records[kind]=dict(issued=active,root=int(len(root_ids)),child=int(len(child_ids)),rhs=len(rhs),
                                   source_aligned=True,runs=len(raw),point_work=read(dest/'run.json')['neural_work_counts'])
        assert records['macro']['root']==records['leaf']['root'] or records['macro']['child']>0
        report[case]=records;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,records,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','model','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product']);control(p.parse_args())
