"""Challenge source provenance using a different visible constructor row with the same e-class at release."""
import argparse
import json
from pathlib import Path
import numpy as np
from study import engine, inputs, load_catalog, pair_joins, read, replace_once, retirement_executor, verify


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    donor=a.ref/'sum-bits/program.json';joins=pair_joins(read(donor))
    for case in a.cases:
        image,p,gold=inputs(a.corpus,a.ref,case);entries=load_catalog(image,p,donor)
        for seed in (1703,1709):
            source=a.paired/f'{case}-{seed}-batch'
            with np.load(source/'neural-output.npz') as n,np.load(source/'compound-output.npz') as c:
                raw=n['raw'];claims=c['claims']
            wins=claims[:,:,7]>0
            # Freeze the locations of previously successful child releases for targeted fault injection.
            # These diagnostics do not contribute to an autonomous generation metric.
            at_release=np.where(wins,claims[:,:,5],0).reshape(-1)
            model=read(a.training/f'train-{seed}'/'policy.json')
            cfg=dict(catalog=entries,rows=2,hidden=8,ranks=8,waves=2,weights=model['roots'],
                     compound=dict(joins=joins,child=model['child'],batch=True,replay=raw))
            folder=a.out/f'{case}-{seed}'
            with retirement_executor(False):
                shader=engine.HERE/'recurrent-generator/compound.metal'
                text='constant int expected_release[]={'+','.join(map(str,at_release))+'};\n'+shader.read_text()
                code="""
        bool forged=false;
        if(expected_release[id]==state[3] && table(rom,entry[3])[1]){
            int last=table(rom,entry[3])[0]-1;
            long semantic=field(rom,lits,meta,dyn,row,last),raw_result=rawfield(rom,lits,meta,dyn,row,last);
            for(int other=head[entry[3]];other>=0;other=meta[6*other+5]){
                if(other==row || meta[6*other+3] || !anchor(meta,other)[4])continue;
                if(rawfield(rom,lits,meta,dyn,other,last)==raw_result)continue;
                if(field(rom,lits,meta,dyn,other,last)!=semantic)continue;
                // Substitute the row, keep the claim's original publication ticket, and let
                // the existing compound_resume version check decide whether the forged input passes.
                c.row=other;row=other;c.verified=state[3];c.next=anchor(meta,other)[4];c.bank=-1000;
                forged=true;break;
            }
        }
"""
                guard='        if(meta[6*row+3] || anchor(meta,row)[4]!=c.ticket){c.status=3;continue;}'
                text=replace_once(text,guard,code+guard+'\n        if(forged){state[5]=30;return;}')
                shader.write_text(text)
                engine.execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,neural=cfg,count_work=True)
            verify(folder,gold,image)
            with np.load(folder/'compound-output.npz') as z:
                updated=z['claims'];rejected=(updated[:,:,3]!=claims[:,:,3]) & wins
                assert np.all(updated[:,:,8][rejected]==3) and np.all(updated[:,:,6][rejected]==-1000)
                assert np.all(~rejected|wins) and np.all(updated[:,:,7][rejected]==0)
                # All fallback-covered effects remain byte-aligned. Other origins may become alternative winners.
                stats=dict(offered_winners=int(wins.sum()),equal_class_wrong_source=int(rejected.sum()),
                           wrong_sources_accepted=0,remaining_child_winners=int((updated[:,:,7]>0).sum()),source_aligned=True,
                           other_winner_changes=int(((updated[:,:,7]!=claims[:,:,7])&~rejected).sum()))
                examples=[]
                for t,lane in zip(*np.nonzero(rejected)):
                    old,new=claims[t,lane],updated[t,lane]
                    assert old[3]!=new[3] and old[4]!=new[10] and old[5]==new[5]
                    examples.append(dict(issue=int(t)+1,release=int(new[5]),valid_row=int(old[3]),claimed_ticket=int(old[4]),
                                         wrong_row=int(new[3]),wrong_ticket=int(new[10]),original_rhs=int(old[7])))
                stats['examples']=examples[:3]
                report[f'{case}/{seed}']=stats
                print(case,seed,stats['equal_class_wrong_source'],stats['offered_winners'],flush=True)
            (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('corpus','ref','reader','training','paired','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    run(p.parse_args())
