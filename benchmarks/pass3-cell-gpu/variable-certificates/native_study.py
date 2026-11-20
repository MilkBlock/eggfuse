"""A CPU policy emits typed port/copy expressions; the native Rust Cell graph materializes and checks them."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

import numpy as np
import torch
from port_model import HERE,Ports,schemas,tensors,forest_policy,inputs,read
sys.path.insert(0,str(HERE.parent/'native-forest'))
from export_cpu import export_inputs,export_model


def write(path,data):path.write_text(json.dumps(data,separators=(',',':'),allow_nan=False))


def cli(binary,source,weights,plan,out,only=False):
    cmd=[str(binary),'--program',str(source),'--output',str(out),'--audit-events',
         '--forest-policy',str(weights),'--forest-inputs',str(plan)]
    if only:cmd.append('--forest-only')
    start=perf_counter_ns();subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
    return (perf_counter_ns()-start)/1e6


def trace(report):
    return [(s['ordinal'],s['ruleset'],s['epoch'],s['executed_bindings'],s['changed'],s['live_cells']) for s in report['steps']]


def py_forward(p,layouts,idx,forest,head):
    frozen=forest_policy.Policy(forest['tables'],forest['rules']);frozen.load_state_dict(forest['state']);frozen.eval()
    candidates=torch.from_numpy(p['candidates']);roots=torch.from_numpy(p['root_x'])
    latent,activations=frozen(roots,torch.from_numpy(p['child_x']),candidates)
    active=activations>=0;universal=torch.as_tensor(p['projections'])[candidates[:,2].long()]>=0
    header=torch.stack((active.int(),candidates[:,0],candidates[:,1],candidates[:,2],candidates[:,3],(active&universal).int()),1).int()
    sha=hashlib.sha256(header.numpy().astype('<i4').tobytes()).hexdigest()
    pairs,inv=np.unique(np.column_stack([idx,p['candidates'][:,0]]),axis=0,return_inverse=True)
    z=tensors(layouts);rows=pairs[:,0]
    logits=head(z['x'][rows],latent[pairs[:,1]],z['eligible'][rows]);selected=logits.argmax(2)
    addr=z['address'][rows,None,:].expand(-1,logits.shape[1],-1)
    return active.numpy(),addr.gather(2,selected[:,:,0:1])[:,:,0][inv].numpy(),addr.gather(2,selected[:,:,1:])[:,:,0][inv].numpy(),sha


def serialize_layout(layouts,ids):
    data=tensors(layouts);x=data['x'].numpy();mask=data['eligible'].numpy();out=[]
    for i,t in enumerate(layouts):
        choices=[]
        for j in range(t['width']):
            choices.append([[int(data['address'][i,k]),x[i,j,k].tolist()] for k in np.flatnonzero(mask[i,j])])
        out.append(dict(choices=choices))
    return dict(layouts=ids.tolist(),templates=out)


def expected_refs(mode,budget,layouts,ids,active,ref,val):
    refs=[];copies=[]
    for i in np.flatnonzero(active):
        width=layouts[ids[i]]['width']
        if not width or mode=='boundary':continue
        fixed=mode in ('fixed','wrong-value');m=budget if fixed else width
        for j in range(m):
            refs.append(65535 if mode=='wrong-reference' or j>=width else int(ref[i,j]))
            if fixed:copies.append(65535 if mode=='wrong-value' or j>=width else int(val[i,j]))
    return refs,copies


def semantics(folder,gold,complete):
    report=read(folder/'report.json');ref=read(gold/'report.json');actual=report['precomputed_forest']
    current=trace(report);source=trace(ref)
    first=next((i+1 for i,(l,r) in enumerate(zip(current,source)) if l!=r),None)
    if first is None and len(current)!=len(source):first=min(len(current),len(source))+1
    if complete:
        assert first is None
        for k in ('rhs','state','writes','events','resumes'):assert read(folder/f'{k}.json')==read(gold/f'{k}.json'),k
    else:
        # The exact completer is disabled. Find an ordered-input divergence even if counts coincide.
        now,old=read(folder/'rhs.json'),read(gold/'rhs.json')
        first=next((i+1 for i,(l,r) in enumerate(zip(now,old)) if l!=r),first)
        assert actual['rhs']==len(actual['children'])+len(actual['static']) and first is not None
    roots={r:o for r,_,o in actual['static']};ordinals=set(roots.values());winners={}
    for id,parent,rid,epoch,ordinal,parent_ordinal in actual['children']:
        assert id not in winners and roots[parent]==parent_ordinal<ordinal and ordinal not in ordinals
        winners[id]=(epoch,ordinal);ordinals.add(ordinal)
    return report,actual,winners,first


def summarize(actual,layouts,ids,active,seen,base,winners):
    ports=actual['ports'];fault=np.asarray(ports['faults']);eligible=np.asarray([layouts[i]['width']>0 for i in ids])&active
    width=np.asarray([layouts[i]['width'] for i in ids]);groups={}
    for i in np.flatnonzero(eligible):
        t=layouts[ids[i]];cold=t['signature'] not in seen
        for key in ('all','cold' if cold else 'seen',f"fields{t['width']}",f"slots{t['slots']}",f"members{t['arity']}"):
            g=groups.setdefault(key,dict(active=0,reference=0,won=0,faults=0,wrong_member=0,wrong_column=0,wrong_value=0))
            g['active']+=1;g['won']+=i in winners;g['reference']+=i in base;g['faults']+=int(fault[i].any())
            for j,label in enumerate(('wrong_member','wrong_column','wrong_value')):g[label]+=int(fault[i,j]>0)
    expected_by_run={};actual_ord=set(w[1] for w in winners.values())
    for _,(run,ordinal) in base.items():expected_by_run.setdefault(run,set()).add(ordinal)
    return dict(cohorts=groups,eligible_reference_children=len(base),neural_children=len(winners),
                compiler_static_roots=len(actual['static']),all_rhs=actual['rhs'],exact=actual['rhs']-len(winners)-len(actual['static']),
                full_nonempty_port_runs=sum(s<=actual_ord for s in expected_by_run.values()),nonempty_port_runs=len(expected_by_run),
                point_reads=actual['point_reads'],attempts=actual['attempts'],
                payload={k:v for k,v in ports.items() if k not in ('faults','visited','starts','widths','refs','copies')},
                reference_overflow=sum(1 for i in base if ports['mode']=='fixed' and width[i]>((ports['extra_reference_slots']//ports['eligible']) if ports['eligible'] else 0)),
                verified_boundaries=len(winners),source_aligned=True)


def main(a):
    torch.set_num_threads(1);a.out.mkdir(parents=True,exist_ok=False);summary={}
    for name in a.cases:
        image,program,_=inputs(a.corpus,a.ref,name);gold=a.gold/f'{name}-native-reference'
        if not (gold/'report.json').exists():
            gold=a.out/f'{name}-native-reference'
            subprocess.run([str(a.build/'runtime'),'--program',str(program),'--output',str(gold),'--audit-events'],check=True,
                           stdout=subprocess.DEVNULL)
            original=a.corpus/name/'observation'
            for k in ('rhs','resumes','writes','state'):assert read(gold/f'{k}.json')==read(original/f'{k}.json')
            def unions(folder):return [[e for e in run if e[0]=='union'] for run in read(folder/'events.json')]
            assert unions(gold)==unions(original)
        packet=forest_policy.packet(image,program); layouts,ids=schemas(image,program,packet)
        template=serialize_layout(layouts,ids);template['stride']=read(image/'device.json')['layout']['WIDTH']
        baseplan=export_inputs(program,image)
        for seed in a.seeds:
            frozen=a.forest/f'policy-{seed}.pt';weights=export_model(frozen)
            head=Ports();head.load_state_dict(torch.load(a.head/f'ports-{seed}.pt',weights_only=True));head.eval()
            weights['variable']=dict(hidden=head.hidden.weight.tolist(),bias=head.hidden.bias.tolist(),parent=head.parent.weight.tolist(),
                                     read=head.read.weight.tolist(),out_bias=head.read.bias.tolist())
            wpath=a.out/f'{name}-{seed}-weights.json';write(wpath,weights)
            active,refs,values,header=py_forward(packet,layouts,ids,torch.load(frozen,weights_only=True),head)
            seen=set(read(a.head/f'train-{seed}.json')['seen'])
            modes=[('boundary','boundary',0),('fixed4','fixed',4),('fixed6','fixed',6),('all','all',0),
                   ('wrong-reference','wrong-reference',0),('wrong-value','wrong-value',6)]
            arms={};plans=[];base=None
            for label,mode,cap in modes:
                plan=a.out/f'{name}-{seed}-{label}-plan.json';write(plan,dict(baseplan,variable=dict(template,mode=mode,capacity=cap)))
                folder=a.out/f'{name}-{seed}-{label}'
                cold_ms=cli(a.build/'runtime',program,wpath,plan,folder)
                report,actual,winners,first=semantics(folder,gold,True)
                ports=actual['ports']
                assert report['neural_policy']['certificate_sha256']==header
                ref,val=expected_refs(mode,cap,layouts,ids,active,refs,values)
                assert ports['refs']==ref and ports['copies']==val,(name,seed,label)
                if base is None:base=winners
                assert all(i in base and base[i]==v for i,v in winners.items())
                arms[label]=summarize(actual,layouts,ids,active,seen,base,winners);arms[label]['cold_cli_ms']=cold_ms
                if label.startswith('wrong'):assert not winners
                else:
                    plans.append(plan);arms[label]['samples_ms']=[];arms[label]['port_samples_ms']=[]
                    no=a.out/f'{name}-{seed}-{label}-no-residual';cli(a.build/'runtime',program,wpath,plan,no,True)
                    rep,unassisted,source,first=semantics(no,gold,False)
                    arms[label]['autonomous']=dict(runs=len(rep['steps']),first_difference=first,rhs=unassisted['rhs'],
                        static=len(unassisted['static']),children=len(source),exact=0)
            timed=[label for label,_,_ in modes if not label.startswith('wrong')]
            session=subprocess.Popen([str(a.build/'session'),str(program),str(wpath),*map(str,plans)],stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,text=True)
            try:
                assert session.stdout.readline().strip()=='ready';expected_digest=None
                for t in range(2*len(timed)):
                    order=list(range(t%len(timed),len(timed)))+list(range(t%len(timed)))
                    for idx in order if t<len(timed) else order[::-1]:
                        session.stdin.write(str(idx)+'\n');session.stdin.flush();z=json.loads(session.stdout.readline())
                        if expected_digest is None:expected_digest=z['digest']
                        arm=arms[timed[idx]]
                        assert z['header']==header and z['children']==arm['neural_children'] and z['digest']==expected_digest
                        arm['samples_ms'].append(z['total_ms']);arm['port_samples_ms'].append(z['ports_ms'])
                session.stdin.write('stop\n');session.stdin.flush();assert session.wait()==0
            finally:
                if session.poll() is None:session.kill();session.wait()
            for label in timed:
                arm=arms[label];arm['median_ms']=median(arm['samples_ms']);arm['median_ports_ms']=median(arm['port_samples_ms'])
            summary[f'{name}/{seed}']=dict(header_sha256=header,arms=arms)
            (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
            print(name,seed,[(k,arms[k]['neural_children'],round(arms[k]['median_ms'],2)) for k in timed],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','forest','head','build','gold','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():main(p.parse_args())
