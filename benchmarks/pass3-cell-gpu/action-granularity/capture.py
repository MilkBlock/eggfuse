"""Record a supervised physical witness rank only after a real source route completed."""
import argparse
import inspect
from pathlib import Path
import sys
import numpy as np

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE));import run
sys.path.insert(0,str(BASE/'recurrent-generator'))
from catalog import load_catalog,read


def replace(source,anchor,new):
    if source.count(anchor)!=1:raise RuntimeError(f'unexpected upstream executor at {anchor}')
    return source.replace(anchor,new)


def capture_fn():
    src=inspect.getsource(run.execute)
    shader_src=(BASE/'executor.metal').read_text()
    raw=replace(shader_src,'if(CERT)witness[pos]=row;', 'if(CERT || NEURAL_LABELS)witness[pos]=row;')
    raw=replace(raw,'labels[l*NEURAL_RANKS+k]=1;break;', '''labels[l*NEURAL_RANKS+k]=1;
                    int suffix=-1;
                    if(rule[0]==2 && path[4]>=0){
                        int actual=witness[1],rank=0;
                        for(int at=head[path[4]];at>=0 && rank<8;at=meta[6*at+5],rank++)if(at==actual){suffix=rank;break;}
                    }
                    labels[RUN_CAP*NEURAL_ACTIONS+l*NEURAL_RANKS+k]=suffix+2;
                    break;''')
    src=replace(src,"    shader=(HERE/'executor.metal').read_text()", "    shader=recording_shader")
    src=replace(src,'if capture_receipts:meta_words+=steps*leaves*ranks','if capture_receipts:meta_words+=2*steps*leaves*ranks')
    src=replace(src,"                extra['receipt']=meta.view", """                suffix_start=offset+steps*leaves*ranks
                extra['suffix_rank']=meta.view(-1)[suffix_start:suffix_start+st[11]*leaves*ranks].reshape(st[11],leaves*ranks).cpu().numpy()
                extra['receipt']=meta.view""")
    ns=dict(run.__dict__,recording_shader=raw);exec(compile(src,str(__file__)+'::execute','exec'),ns);return ns['execute']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','original','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);execute=capture_fn()
    for case,info in read(a.corpus/'collection.json').items():
        if info['split'] not in ('train','development'):continue
        image=a.corpus/case/'input';program=a.corpus/case/'program.json'
        entries=load_catalog(image,program,a.ref/'sum-bits/program.json')
        dest=a.out/case
        execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,neural=dict(catalog=entries,rows=2,ranks=8,
                hidden=8,capture=True,receipt_labels=True))
        with np.load(dest/'neural-inputs.npz') as z,np.load(a.original/case/'training.npz') as old:
            np.testing.assert_array_equal(z['features'],old['features']);np.testing.assert_array_equal(z['receipt'],old['receipt'])
            valid=z['suffix_rank']-2
            np.savez_compressed(dest/'ranks.npz',rank=valid.astype(np.int8))
            print(case,int((valid>=0).sum()),len(valid),flush=True)
