"""One sealed universal-parent proof stream, three verifier placements plus a full-state-write ablation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from statistics import median
import struct
import subprocess
import sys
from time import perf_counter_ns

import numpy as np
import torch

HERE=Path(__file__).resolve().parent;GPU=HERE.parent
sys.path.insert(0,str(GPU/'native-forest'))
from certificate import Generator
from export_cpu import export_model,export_inputs
sys.path.insert(0,str(GPU/'whole-pass-generation'))
from adapter import specialize
_spec=importlib.util.spec_from_file_location('delta_forest_reference',GPU/'whole-pass-generation/study.py')
_module=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_module)
open_generator,audit=_module.open_generator,_module.audit
sys.path.insert(0,str(GPU/'recurrent-generator'))
from capture import inputs,verify,read
from feedback_study import bind_session
from events_audit import align
from endpoint import endpoint


def write(p,d):p.write_text(json.dumps(d,separators=(',',':'))+'\n')
def native_cli(binary,program,out,args,mode=None):
    env=dict(os.environ)
    if mode:env['EGGFUSE_PROOF_SIDECAR']=mode
    else:env.pop('EGGFUSE_PROOF_SIDECAR',None)
    subprocess.run([str(binary),'--program',str(program),'--output',str(out),'--audit-events',*args],check=True,
                   env=env,stdout=subprocess.DEVNULL)


def native_stats(folder,gold,residual):
    r=read(folder/'report.json');src=read(gold/'report.json')
    info=r['precomputed_forest']
    actual=read(folder/'rhs.json');reference=read(gold/'rhs.json')
    first=next((i+1 for i,(a,b) in enumerate(zip(actual,reference)) if a!=b),None)
    if first is None and len(actual)!=len(reference):first=min(len(actual),len(reference))+1
    if residual:
        assert first is None
        for k in ('rhs','writes','resumes','state','events'):assert read(folder/f'{k}.json')==read(gold/f'{k}.json')
    else:assert first and info['rhs']==len(info['static'])+len(info['children'])
    parents={rid:ordinal for rid,_,ordinal in info['static']};ordinals=set(parents.values());ids=set()
    for id,parent,rid,epoch,o,source in info['children']:
        assert o not in ordinals and id not in ids and parents[parent]==source<o
        ordinals.add(o);ids.add(id)
    return dict(runs=len(r['steps']),source_rhs=sum(s['executed_bindings'] for s in src['steps']),
        actual_rhs=info['rhs'],static=len(parents),neural_children=len(ids),exact=info['rhs']-len(ordinals),
        first_divergence=first,sidecar=info['sidecar'],winning_ids=sorted(ids),
        child_ordinals=sorted((v[0],v[4]) for v in info['children']),source_aligned=residual)


def readline(proc):
    s=proc.stdout.readline()
    if not s:raise RuntimeError('native service stopped')
    return s.decode().strip()
def words(proc,raw):
    proc.stdin.write(struct.pack('<I',len(raw)));proc.stdin.write(raw);proc.stdin.flush()


def main(a):
    torch.set_num_threads(1);a.out.mkdir(parents=True,exist_ok=False);reports={}
    for name in a.cases:
        image,program,metal_gold=inputs(a.corpus,a.ref,name)
        gold=a.native/f'{name}-native-reference'
        independent=a.ref/f'oracle-{name}' if name in ('sum-bits','dot-product') else a.corpus/name/'observation'
        if not gold.is_dir():
            gold=a.out/f'{name}-native-reference';native_cli(a.build/'runtime',program,gold,[])
            for k in ('state','rhs','resumes','writes'):assert read(gold/f'{k}.json')==read(independent/f'{k}.json')
            unions=lambda path:[[e for e in r if e[0]=='union'] for r in read(path/'events.json')]
            assert unions(gold)==unions(independent)
        initial=read(independent/'binding-audit.json')['initial'] if (independent/'binding-audit.json').exists() else read(independent/'repair-inputs.json')
        initial_path=a.out/f'{name}-initial.json'
        initial.update(schema='eggfuse-repair-inputs/v1',program_sha256=read(program)['sha256']);write(initial_path,initial)
        for seed in a.seeds:
            checkpoint=a.weights/f'policy-{seed}.pt';trained=torch.load(checkpoint,weights_only=True)
            cp=export_model(checkpoint);plan=export_inputs(program,image)
            w_path=a.out/f'{name}-{seed}-weights.json';p_path=a.out/f'{name}-inputs.json';write(w_path,cp);write(p_path,plan)
            generator=Generator(program,image,trained,'mps')
            def issue():
                roots,child,latent=generator.emit()
                child[:,5]=torch.where((child[:,0]!=0)&(child[:,5]==0),-2,child[:,5])
                return child.cpu().contiguous().numpy().astype('<i4',copy=False).tobytes()
            frozen=issue();arr=np.frombuffer(frozen,'<i4').reshape(-1,6);sha=hashlib.sha256(frozen).hexdigest()
            layout=dict(schema='eggfuse.sealed-forest/v1',program_sha256=generator.digest,roots=generator.plan['roots'],
                        catalog=generator.catalog,children=arr.tolist())
            cert=a.out/f'{name}-{seed}-sealed.json';write(cert,layout)
            assisted={};controls={};sessions={}
            for arm,mode in [('cpu-rust',None),('gpu-rust',None),('delta','delta'),('snapshot','snapshot'),('corrupt','wrong-port')]:
                dest=a.out/f'{name}-{seed}-{arm}'
                args=['--forest-policy',str(w_path),'--forest-inputs',str(p_path)] if arm=='cpu-rust' else ['--precomputed-forest',str(cert)]
                native_cli(a.build/'runtime',program,dest,args,mode)
                m=native_stats(dest,gold,True)
                if arm=='cpu-rust':
                    assert read(dest/'report.json')['neural_policy']['certificate_sha256']==sha
                elif arm=='corrupt':
                    assert m['neural_children']==0 and m['sidecar']['device_projected_replies_delivered']==0
                else:
                    assert m['child_ordinals']==assisted['cpu-rust']['child_ordinals']
                if mode:
                    assert m['sidecar']['device_projected_replies_delivered']>=m['neural_children']
                assisted[arm]=m
                if arm in ('cpu-rust','delta'):
                    no=dest.with_name(dest.name+'-only');native_cli(a.build/'runtime',program,no,args+['--forest-only'],mode)
                    controls[arm]=native_stats(no,gold,False)
            assert assisted['delta']['sidecar']['state_write_bytes']<assisted['snapshot']['sidecar']['state_write_bytes']
            assert controls['cpu-rust']['child_ordinals']==controls['delta']['child_ordinals']
            root=generator.plan
            for complete in (True,False):
                emit,saved=open_generator(root,trained,'proof-only')
                execute=specialize(root,emit,complete,events=True)
                dest=a.out/f"{name}-{seed}-metal{'-only' if not complete else ''}"
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,
                        measure_resident=bind_session(sessions,'gpu-metal') if complete else None)
                raw=saved[0].cpu().numpy();np.testing.assert_array_equal(raw,arr)
                stats=audit(dest,metal_gold,root,raw,complete)
                if complete:verify(dest,metal_gold,image);assisted['gpu-metal']=stats
                else:controls['gpu-metal']=stats
                rust=a.out/f"{name}-{seed}-delta{'-only' if not complete else ''}"
                ordering=align(program,image/'ingress.json',dest,rust,rust,initial_snapshot=initial_path)
                report_path=dest/'alignment.json';write(report_path,ordering)
                cross=endpoint(image/'ingress.json',dest,rust,report_path)
                assert cross['acceptance']=='pass' and cross['full_typed_graph_equal']
                with np.load(dest/'forest.npz') as z:
                    gpu_ids=sorted((int(i),int(z['children'][i,2])) for i in np.flatnonzero(z['children'][:,2]))
                cpu_ids=(assisted if complete else controls)['delta']['child_ordinals']
                assert gpu_ids==cpu_ids,(name,seed,complete,len(gpu_ids),len(cpu_ids))
                stats['cross_typed_graph']=True;stats['cross_ordinals']=True;stats['cross_runs']=ordering['compared']
            procs={};samples={k:[] for k in ('cpu-rust','gpu-rust','delta','snapshot','gpu-metal')};graph_hash=None
            try:
                for arm in ('cpu-rust','gpu-rust','delta','snapshot'):
                    env=dict(os.environ)
                    if arm in ('delta','snapshot'):env['EGGFUSE_PROOF_SIDECAR']=arm
                    else:env.pop('EGGFUSE_PROOF_SIDECAR',None)
                    cmd=[a.build/'cpu_session',program,w_path,p_path] if arm=='cpu-rust' else [a.build/'session',program,cert]
                    procs[arm]=subprocess.Popen(list(map(str,cmd)),env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
                names=list(samples)
                for t in range(2*len(names)):
                    k=t%len(names);order=names[k:]+names[:k]
                    for arm in order if t<len(names) else order[::-1]:
                        if arm=='gpu-metal':
                            reset,infer,buf=sessions[arm];reset();torch.mps.synchronize()
                            start=perf_counter_ns();infer();torch.mps.synchronize();ms=(perf_counter_ns()-start)/1e6
                            state=buf['state'].cpu().tolist();assert state[7] and not state[5]
                            with np.load(metal_gold/'output.npz') as z:
                                for label,idx in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                                    value,truth=buf[label][:state[idx]].cpu().numpy(),z[label]
                                    if label=='rhs':
                                        np.testing.assert_array_equal(value[:,:2],truth[:,:2]);value,truth=value[:,4:],truth[:,4:]
                                    np.testing.assert_array_equal(value,truth)
                            samples[arm].append(dict(ms=ms));continue
                        proc=procs[arm];assert readline(proc)=='ready'
                        start=perf_counter_ns()
                        if arm=='cpu-rust':proc.stdin.write(b'run\n');proc.stdin.flush();emit_ms=None
                        else:
                            data=issue();emit_ms=(perf_counter_ns()-start)/1e6;words(proc,data)
                        outcome=json.loads(readline(proc));ms=(perf_counter_ns()-start)/1e6
                        if arm!='cpu-rust':assert data==frozen
                        assert outcome['children']==assisted[arm]['neural_children']
                        digest=readline(proc)
                        if graph_hash is None:graph_hash=digest
                        assert digest==graph_hash
                        if arm=='cpu-rust':assert outcome['hash']==sha;emit_ms=outcome['forward_ms']
                        samples[arm].append(dict(ms=ms,emit_ms=emit_ms,validation_ms=outcome['validation_ms'],
                            inference_ms=outcome['inference_ms'],sidecar=outcome.get('sidecar')))
                for arm,proc in procs.items():
                    assert readline(proc)=='ready'
                    if arm=='cpu-rust':proc.stdin.write(b'stop\n');proc.stdin.flush()
                    else:words(proc,b'')
                    assert proc.wait()==0
            finally:
                for proc in procs.values():
                    if proc.poll() is None:proc.kill();proc.wait()
            reports[f'{name}/{seed}']=dict(shared_sha=sha,slots=len(arr),active=int(arr[:,0].sum()),
                universal_active=int((arr[:,5]==1).sum()),certificate_bytes=len(frozen),
                assisted=assisted,no_residual=controls,samples=samples,median_ms={k:median(s['ms'] for s in rows) for k,rows in samples.items()})
            write(a.out/'results.json',reports)
            print(name,seed,assisted['delta']['neural_children'],reports[f'{name}/{seed}']['median_ms'],flush=True)
            sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','weights','build','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():main(p.parse_args())
