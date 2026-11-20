"""Check the conservative recurrent gate with no residual work in its entire admitted cohort."""
import argparse,json
from pathlib import Path
from statistics import median
import subprocess
import numpy as np
from capture import paths,read,dump,launch,aligned
from study import attribution
from calibrate import prepare


def independent(seq,m,floors):
    H=np.asarray(m['h'],np.float32);out=np.asarray(m['out'],np.float32);rb=np.asarray(m['rbias'],np.float32)
    U=np.asarray(m['recurrent'],np.float32);T=np.asarray(m['update'],np.float32);h=np.zeros(4,np.float32)
    total=selected=positive=accepted=0
    for rid,n,hidden,c,y,fresh in seq:
        score=np.tanh(hidden+h@H.T)@out+m['bias']+m['rules'][rid%len(m['rules'])]
        mask=score>=floors[rid];count=int(c@mask)
        h=np.tanh(U@h+T@np.array([min(n,128)/128,count/n,fresh,(rid%64)/63],np.float32)+rb)
        total+=n;selected+=count;positive+=int(y.sum());accepted+=int(y@mask)
    return [total,selected,positive,accepted]


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    for n in a.cases:
        program,gold=paths(a.corpus,a.ref,n);trace=a.ref/f'release-{n}';cap=a.capture/n
        for seed in (1703,1709):
            arms={};files={}
            for label in ('certified','guarded','delta','bucket','exact'):
                if label=='exact':files[label]='exact';arms[label]={};continue
                if label=='certified':cfg=read(Path(str(a.cert).replace('SEED',str(seed)))/'config.json')
                elif label=='guarded':cfg=read(a.learned/f'{seed}-high.json');cfg['mode']='guarded'
                elif label=='bucket':cfg=read(a.bucket/f'{seed}-bucket-0.5.json')
                else:cfg=dict(mode='delta',model=None)
                cfg.update(complete_unsupported=True,residual=label=='bucket')
                path=a.out/f'{n}-{seed}-{label}.json';dump(path,cfg);files[label]=str(path)
                folder=a.out/f'{n}-{seed}-{label}';launch(a.build/'runtime',program,folder,path);aligned(folder,gold)
                rep=read(folder/'report.json')['single_witness'];work=rep['work'];model=cfg.get('model')
                proof=attribution(folder,trace,program,model,cap)
                # Independently count per-Run proposals using the already recorded prospective observations.
                diag=None
                if label in ('certified','bucket'):
                    diag=independent(prepare(cap/'report.json',model),model,rep['floors'])
                    assert diag[:2]==work[:2] and diag[3]==work[5]
                if label!='bucket':assert work[2]==work[1] and work[6]==0
                if label=='certified':assert rep['guard_counts'][0]==work[0]-work[1] and not rep['guarded_ordinals']
                arms[label]=dict(rhs=rep['rhs'],claimed=len(rep['committed']),work=work,guard=rep['guard_counts'],
                    pure_model=0 if label=='delta' else len(rep['committed'])-len(rep['guarded_ordinals']),
                    guard_credited=len(rep['guarded_ordinals']),independent=diag,provenance=proof,source_aligned=True,
                    residual_within=cfg['residual'],residual_outside=True)
                if label=='certified':
                    assert len(rep['committed'])==read(cap/'report.json')['single_witness']['work'][5]
            labels=list(arms);svc=subprocess.Popen([str(a.build/'session'),str(program)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                assert svc.stdout.readline().strip()=='ready';digest=None
                for trial in range(2*len(labels)):
                    k=trial%len(labels);order=labels[k:]+labels[:k]
                    for label in order if trial<len(labels) else order[::-1]:
                        svc.stdin.write(files[label]+'\n');svc.stdin.flush();v=json.loads(svc.stdout.readline())
                        if digest is None:digest=v['graph']
                        assert v['graph']==digest and (label=='exact' or v['single']==arms[label]['claimed'])
                        arms[label].setdefault('ms',[]).append(v['ms'])
                svc.stdin.write('stop\n');svc.stdin.flush();assert svc.wait()==0
            finally:
                if svc.poll() is None:svc.kill();svc.wait()
            for v in arms.values():v['median_ms']=median(v['ms'])
            result[f'{n}/{seed}']=arms;(a.out/'results.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
            print(n,seed,[(k,v['claimed'],v['work'][1],v['work'][0],v['guard_credited']) for k,v in arms.items() if k!='exact'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','build','learned','bucket','cert','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product']);run(p.parse_args())
