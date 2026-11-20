"""Learn a fixed record containing typed values selected before any source graph execution."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import numpy as np
import torch
from torch import nn
from native_study import read,write,inputs,cli,semantics,export_inputs,export_model,schemas,serialize_layout,forest_policy,Ports


def request(t,f):
    literal=f['value'][1] if f['value'][0]=='literal' else None
    try:number=float(literal)
    except (TypeError,ValueError):number=0.
    return [f['query']/2,f['member']/2,f['col']/6,t['arity']/2,t['width']/10,t['slots']/10,
            float(f['result']),float(literal is not None),float(np.clip(number,-10,10))/10,
            float(f['sort']=='i64'),float(f['sort']=='Expr'),float(f['sort']=='bool'),
            float(f['sort']=='Type'),f['table']/400]


def make_files(a,n,seed,mode,cap,raw_head=None):
    image,program,_=inputs(a.corpus,a.ref,n);p=forest_policy.packet(image,program)
    layouts,ids=schemas(image,program,p)
    model=export_model(a.forest/f'policy-{seed}.pt')
    net=Ports();net.load_state_dict(torch.load(a.head/f'ports-{seed}.pt',weights_only=True))
    model['variable']=dict(hidden=net.hidden.weight.tolist(),bias=net.hidden.bias.tolist(),parent=net.parent.weight.tolist(),
                           read=net.read.weight.tolist(),out_bias=net.read.bias.tolist(),raw=raw_head)
    plan=export_inputs(program,image);desc=serialize_layout(layouts,ids)
    requests=[[dict(features=request(t,f),sort=f['sort']) for f in t.get('logical',[])] for t in layouts]
    for temp,rs in zip(desc['templates'],requests):temp['requests']=rs
    desc.update(mode=mode,capacity=cap,stride=read(image/'device.json')['layout']['WIDTH'])
    plan['variable']=desc
    stem=f'{n}-{seed}-{mode}-{cap}'
    weights=a.out/f'{stem}-weights.json';config=a.out/f'{stem}-inputs.json'
    write(weights,model);write(config,plan)
    return program,p,layouts,ids,requests,model,weights,config


def latent(p,model):
    return np.tanh(p['root_x']@np.asarray(model['root_weight'],np.float32).T+np.asarray(model['root_bias'],np.float32))


def predictor_input(f,root,c):
    i,e,r,pivot=map(int,c[:4])
    return [*f,*map(float,root),i/8,e/1024,r/1024,pivot/16]


def fit(a,seed):
    cases=[n for n,t in read(a.corpus/'collection.json').items() if t['split']=='train']
    seen=set(read(a.head/f'train-{seed}.json')['seen']);xs=[];ys=[];sorts=[];shapes=set()
    for n in cases:
        source,p,layouts,ids,req,model,w,plan=make_files(a,n,seed,'collect-values',32)
        folder=a.out/f'{n}-{seed}-train';cli(a.build/'runtime',source,w,plan,folder)
        gold=a.corpus/n/'observation'
        for k in ('rhs','resumes','writes','state'):assert read(folder/f'{k}.json')==read(gold/f'{k}.json')
        r=read(folder/'report.json')['precomputed_forest'];v=r['ports'];roots=latent(p,model)
        for id,*_ in r['children']:
            t=layouts[ids[id]]
            if t['signature'] not in seen:continue
            shapes.add(t['signature']);c=p['candidates'][id];start=v['starts'][id]
            for col,q in enumerate(req[t['idx']]):
                value=v['training_values'][start+col];assert value is not None
                xs.append(predictor_input(q['features'],roots[c[0]],c))
                ys.append(json.dumps(value,sort_keys=True,separators=(',',':')));sorts.append(q['sort'])
    vocabulary=sorted(set(zip(sorts,ys)));target={v:j for j,v in enumerate(vocabulary)}
    torch.manual_seed(seed);rng=np.random.default_rng(seed)
    net=nn.Sequential(nn.Linear(30,32),nn.Tanh(),nn.Linear(32,len(vocabulary)))
    x=torch.tensor(xs,dtype=torch.float32);y=torch.tensor([target[v] for v in zip(sorts,ys)])
    mask=torch.tensor([[group==kind for kind,_ in vocabulary] for group in sorts])
    opt=torch.optim.Adam(net.parameters(),lr=.01)
    for _ in range(400):
        ids=rng.integers(0,len(x),64);logits=net(x[ids]).masked_fill(~mask[ids],-1e4)
        loss=nn.functional.cross_entropy(logits,y[ids]);opt.zero_grad();loss.backward();opt.step()
    model=dict(hidden=net[0].weight.tolist(),bias=net[0].bias.tolist(),output=net[2].weight.tolist(),out_bias=net[2].bias.tolist(),
               classes=[(sort,json.loads(value)) for sort,value in vocabulary])
    write(a.out/f'raw-{seed}.json',model)
    return model,dict(programs=cases,shapes=sorted(shapes),labeled_fields=len(ys),typed_classes=len(vocabulary),
                      params=sum(p.numel() for p in net.parameters()),updates=400)


def study(a):
    torch.set_num_threads(1);a.out.mkdir(parents=True,exist_ok=False);data={}
    for seed in (1703,1709):
        head,training=fit(a,seed)
        for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
            folder=a.anchors if n in ('sum-bits','dot-product') else a.heldout
            gold=a.gold/f'{n}-native-reference'
            if not gold.is_dir():gold=folder/f'{n}-native-reference'
            base=read(folder/f'{n}-{seed}-boundary'/'report.json')['precomputed_forest']['children']
            arm={};plans=[];shapes=0
            for cap in (4,6):
                source,p,layout,ids,req,policy,w,plan=make_files(a,n,seed,'direct',cap,head)
                out=a.out/f'{n}-{seed}-direct{cap}';cold=cli(a.build/'runtime',source,w,plan,out)
                report,observed,won,_=semantics(out,gold,True)
                ports=observed['ports'];vocab={(s,json.dumps(value,sort_keys=True,separators=(',',':'))) for s,value in head['classes']}
                # Reconstruct the class choices offline without any source-run data.
                ild=latent(p,policy);W=np.asarray(head['hidden'],np.float32);bias=np.asarray(head['bias'],np.float32)
                result_w=np.asarray(head['output'],np.float32);out_bias=np.asarray(head['out_bias'],np.float32)
                # Separate diagnostic materializes ground truth only after the production direct run is finished.
                src2,_,_,_,_,_,cw,cp=make_files(a,n,seed,'collect-values',32)
                collect=a.out/f'{n}-{seed}-truth'
                if not (collect/'report.json').exists():cli(a.build/'runtime',src2,cw,cp,collect)
                truth=read(collect/'report.json')['precomputed_forest']['ports']
                total_fields=in_vocab=correct=eligible=covered=0;seen=set(training['shapes']);cohort={}
                for id,*_ in base:
                    t=layout[ids[id]]
                    if t['width']>cap:continue
                    eligible+=1;all_in=True;all_right=True;c=p['candidates'][id]
                    start=truth['starts'][id]
                    for j,q in enumerate(req[ids[id]]):
                        value=truth['training_values'][start+j];assert value is not None
                        present=(q['sort'],json.dumps(value,sort_keys=True,separators=(',',':'))) in vocab
                        total_fields+=1;in_vocab+=present;all_in &= present
                        typ=[i for i,(s,_) in enumerate(head['classes']) if s==q['sort']]
                        features=np.asarray(predictor_input(q['features'],ild[c[0]],c),np.float32)
                        pred=None if not typ else head['classes'][typ[int((result_w[typ]@np.tanh(W@features+bias)+out_bias[typ]).argmax())]][1]
                        correct+=int(pred==value);all_right &= pred==value
                    covered+=int(all_in)
                    # Any correct native submission requires every direct predicted value to agree.
                    if id in won:assert all_right
                    kind='seen' if t['signature'] in seen else 'cold';g=cohort.setdefault(kind,[0,0,0])
                    g[0]+=1;g[1]+=int(all_in);g[2]+=int(id in won)
                no=a.out/f'{n}-{seed}-direct{cap}-no';cli(a.build/'runtime',source,w,plan,no,True)
                _,unassisted,aut,first=semantics(no,gold,False)
                arm[cap]=dict(children=len(won),reference=len(base),eligible_width=eligible,capacity_overflow=len(base)-eligible,
                    payload_reference_slots=ports['extra_reference_slots'],typed_slots=ports['typed_value_slots'],
                    values_emitted_before_run1=ports['typed_values_materialized'],copy_slots=ports['value_copy_slots'],
                    type_vocabulary_fields=in_vocab,total_fields=total_fields,correct_fields=correct,
                    full_slots_in_vocab=covered,cohorts=cohort,exact=observed['rhs']-len(won)-len(observed['static']),
                    source_aligned=True,header=report['neural_policy']['certificate_sha256'],samples=[],port_ms=[],cold_cli_ms=cold,
                    autonomous=dict(first=first,rhs=unassisted['rhs'],children=len(aut),exact=0))
                plans.append(plan)
            proc=subprocess.Popen([str(a.build/'session'),str(source),str(w),*map(str,plans)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            assert proc.stdout.readline().strip()=='ready'
            try:
                for trial in range(8):
                    for idx in ((0,1) if trial%2==0 else (1,0)):
                        proc.stdin.write(str(idx)+'\n');proc.stdin.flush()
                        result=json.loads(proc.stdout.readline());v=arm[(4,6)[idx]]
                        assert result['children']==v['children'] and result['header']==v['header']
                        v['samples'].append(result['total_ms']);v['port_ms'].append(result['ports_ms'])
                proc.stdin.write('stop\n');proc.stdin.flush();assert proc.wait()==0
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
            for v in arm.values():v['median_ms']=median(v['samples']);v['median_port_ms']=median(v['port_ms'])
            data[f'{n}/{seed}']=dict(training=training,arms=arm)
            (a.out/'results.json').write_text(json.dumps(data,indent=1)+'\n')
            print(n,seed,[(cap,v['children'],v['full_slots_in_vocab'],v['eligible_width']) for cap,v in arm.items()],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','forest','head','build','gold','anchors','heldout','out'):parser.add_argument(k,type=Path)
    study(parser.parse_args())
