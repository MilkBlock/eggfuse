"""Train the bounded repair catalog on four families, freeze it, then run paired Metal arms."""
import argparse,hashlib,json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import numpy as np
import torch
from bake import Trace,candidates
from collect import read
from device import execute_case,files


def write(path,data):
    path.write_text(json.dumps(data,indent=1)+'\n')


@torch.inference_mode()
def study(case,arms,args,dest,repeats):
    dest.mkdir(parents=True,exist_ok=False)
    sessions={};result={}
    _,_,reference=files(args.corpus,args.reference,case)
    with np.load(reference/'output.npz') as z:
        gold={k:z[k] for k in ('runs','rhs','writes','resumes')}
    for label,arm in arms.items():
        edges,mode,members=arm[:3]
        sparse=len(arm)>3 and arm[3]
        nested=len(arm)>4 and arm[4]
        solo=len(arm)>5 and arm[5]
        def capture(infer,buf,*unused):
            snapshots={k:buf[k].clone() for k in ('state','regs','meta','dyn','head','wm')}
            def reset():
                for k,v in snapshots.items():buf[k].copy_(v)
                for k in ('count','rhs','writes','runs','resumes'):buf[k].zero_()
            sessions[label]=reset,infer,buf
        # Work accounting is a separate run; each release and audit endpoint
        # is compared to the independently aligned physical GPU reference.
        counted=execute_case(args.corpus,args.reference,args.weights,case,dest/(label+'-audit'),
                             edges,mode,members,count=True,sparse_words=sparse,nested=nested,solo=solo)
        execute_case(args.corpus,args.reference,args.weights,case,dest/label,edges,mode,members,
                     count=False,resident=capture,sparse_words=sparse,nested=nested,solo=solo)
        c=counted['co_repair']['counters']
        result[label]=dict(samples_ms=[],instances=c[0],readers=c[1],notifications=c[2],
            group_wakes=c[3],reader_wake_expansions=c[4],mask_repairs=c[5],
            port_mask_reads=c[6],result_only_masks=c[13],key_probes=c[7],collision_tests=c[8],collisions=c[9],notification_word_tests=counted['state'][74],repair_rows=counted['state'][55],
            directory_bytes=counted['co_repair']['extra_meta_bytes'],
            summary_bytes=counted['co_repair']['extra_summary_bytes'],summary_reads=c[14],summary_updates=c[15],
            runs=counted['completed'],exact=True)
    labels=list(arms)
    for i in range(repeats):
        order=labels[i%len(labels):]+labels[:i%len(labels)]
        for label in order if (i//len(labels))%2==0 else order[::-1]:
            reset,infer,buf=sessions[label]
            reset();torch.mps.synchronize()
            start=perf_counter_ns();infer();torch.mps.synchronize()
            elapsed=(perf_counter_ns()-start)/1e6
            st=buf['state'].cpu().tolist()
            assert not st[5] and st[7] and st[11]==len(gold['runs'])
            for k,j in [('rhs',9),('writes',10),('resumes',16),('runs',11)]:
                v=buf[k][:st[j]].cpu().numpy();w=gold[k]
                if k=='rhs':
                    np.testing.assert_array_equal(v[:,:2],w[:,:2])
                    v,w=v[:,4:],w[:,4:]
                np.testing.assert_array_equal(v,w,err_msg=k)
            result[label]['samples_ms'].append(elapsed)
    for item in result.values():item['median_ms']=median(item['samples_ms'])
    print(case,{k:round(v['median_ms'],2) for k,v in result.items()},flush=True)
    return result


def main(args):
    folder=args.out;folder.mkdir(parents=True,exist_ok=False)
    collection=read(args.corpus/'collection.json')
    training=[n for n,c in collection.items() if c['split']=='train']
    assert len(training)==4
    traces=[Trace(args.corpus,args.reference,args.profiles,n) for n in training]
    catalogs,meta=candidates(traces,args.budget)
    # Equal-budget portfolio, measured on the training sources. Prefer the
    # candidate with the smallest family-average paired cost relative to row.
    unique={}
    for name,lib in catalogs.items():
        if lib not in unique.values():unique[name]=lib
    train_arms={'row':([],1,1),**{k:(v,3,3) for k,v in unique.items()}}
    calibration={}
    for n in training:
        calibration[n]=study(n,train_arms,args,folder/'calibrate'/n,len(train_arms)*2)
        write(folder/'training.json',calibration)
    price={k:sum(median((u-b)/b for u,b in zip(calibration[n][k]['samples_ms'],calibration[n]['row']['samples_ms']))
                 for n in training)/len(training) for k in unique}
    best=min(price,key=lambda k:(price[k],k))
    frozen=dict(training=training,budget=args.budget,calibration=price,chosen=best,catalogs=catalogs,**meta)
    write(folder/'catalog.json',frozen)
    digest=hashlib.sha256((folder/'catalog.json').read_bytes()).hexdigest()
    arms={'row':([],1,1),'continuation':(catalogs['continuation'],3,3),'joint':(catalogs['joint'],3,3),
          'priced':(unique[best],3,3),'one-reader':(unique[best],3,2),'instance':(unique[best],2,3)}
    report={}
    for n,c in collection.items():
        if c['split']=='train':continue
        assert hashlib.sha256((folder/'catalog.json').read_bytes()).hexdigest()==digest
        t=Trace(args.corpus,args.reference,args.profiles,n)
        records=study(n,arms,args,folder/'paired'/n,len(arms)*2)
        for k,(lib,mode,members) in arms.items():
            predicted=t.group(lib,members)
            assert predicted['attached']==records[k]['readers'],(n,k,predicted,records[k])
            records[k]['trace_credit']=predicted
        report[n]=dict(split=c['split'],program=c['program'],catalog_sha256=digest,arms=records)
        write(folder/'results.json',report)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','reference','weights','profiles','out'):p.add_argument(k,type=Path)
    p.add_argument('--budget',type=int,default=8)
    main(p.parse_args())
