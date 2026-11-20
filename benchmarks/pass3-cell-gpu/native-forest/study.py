"""The same sealed typed forest on CPU/Rust, GPU/Rust, GPU/Metal. No CPU-policy/Metal arm."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import struct
import subprocess
import sys
from time import perf_counter_ns

import numpy as np
import torch

from certificate import Generator
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'whole-pass-generation'))
from adapter import specialize
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'recurrent-generator'))
from capture import inputs,verify,read
from events_audit import align
from endpoint import endpoint


def cli(binary,program,dest,packet=None,only=False):
    args=[str(binary),'--program',str(program),'--output',str(dest),'--audit-events']
    if packet:args+=['--precomputed-forest',str(packet)]
    if only:args+=['--forest-only']
    start=perf_counter_ns();proc=subprocess.run(args,capture_output=True,text=True)
    if proc.returncode:raise RuntimeError(proc.stderr[-8192:])
    return (perf_counter_ns()-start)/1e6


def source_trace(folder):
    report=read(folder/'report.json')
    return [(s['ordinal'],s['ruleset'],s['epoch'],s['executed_bindings'],s['changed']) for s in report['steps']]


def audit_native(folder,gold,completion):
    trace=source_trace(folder);official=source_trace(gold)
    first=next((i+1 for i,(a,b) in enumerate(zip(trace,official)) if a!=b),None)
    if first is None and len(trace)!=len(official):first=min(len(trace),len(official))+1
    record=read(folder/'report.json')['precomputed_forest']
    total=sum(s[3] for s in trace)
    assert record['rhs']==total,(total,record['rhs'])
    root_ord={r:o for r,_,o in record['static']}
    assert len(root_ord)==len(record['static'])
    used=set(root_ord.values());ids=set()
    for id,parent,rid,epoch,ordinal,p_ordinal in record['children']:
        assert id not in ids and ordinal not in used and root_ord[parent]==p_ordinal<ordinal
        ids.add(id);used.add(ordinal)
    if completion:
        assert first is None,first
        for k in ('state','rhs','resumes','writes','events'):
            assert read(folder/f'{k}.json')==read(gold/f'{k}.json'),k
    else:assert total==len(used) and first is not None
    return dict(runs=len(trace),rhs=total,children=len(ids),compiler_roots=len(root_ord),exact=total-len(used),
                first_divergence=first,attempts=record['attempts'],point_reads=record['point_reads'])


def read_line(proc):
    answer=proc.stdout.readline()
    if not answer:raise RuntimeError('native forest service stopped: '+proc.stderr.read().decode()[-2048:])
    return answer.decode().strip()


def send_words(proc,words):
    proc.stdin.write(struct.pack('<I',len(words)));proc.stdin.write(words);proc.stdin.flush()


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    torch.set_num_threads(1)
    for case in a.cases:
        image,program,metal_gold=inputs(a.corpus,a.ref,case)
        native_gold=a.ref/f'events-{case}' if case in ('sum-bits','dot-product') else a.corpus/case/'observation'
        origin_case=a.ref/f'oracle-{case}' if case in ('sum-bits','dot-product') else a.corpus/case/'observation'
        # Only use the independent CPU observer's input identity map after both executions.
        initial_path=a.out/f'{case}-initial.json'
        if (origin_case/'binding-audit.json').exists():initial=read(origin_case/'binding-audit.json')['initial']
        else:initial=read(origin_case/'repair-inputs.json')
        native_source=read(origin_case/'report.json')['program_sha256']
        assert native_source==read(program)['sha256']
        initial.update(schema='eggfuse-repair-inputs/v1',program_sha256=native_source)
        initial_path.write_text(json.dumps(initial,separators=(',',':')))
        base=a.out/f'{case}-native-reference'
        cli(a.runtime,program,base)
        for key in ('state','rhs','resumes','writes'):
            if (native_gold/f'{key}.json').exists():assert read(base/f'{key}.json')==read(native_gold/f'{key}.json'),key
        if (native_gold/'events.json').is_file():
            def unions(folder):return [[v for v in events if v[0]=='union'] for events in read(folder/'events.json')]
            assert unions(base)==unions(native_gold)
        for seed in a.seeds:
            weights=torch.load(a.weights/f'policy-{seed}.pt',weights_only=True)
            gen={dev:Generator(program,image,weights,dev) for dev in ('cpu','mps')}
            reports={'native-reference':dict(inference_ms=1000*read(base/'report.json')['inference_seconds'],runs=len(source_trace(base)),
                              runtime_sha256=hashlib.sha256(a.runtime.read_bytes()).hexdigest(),service_sha256=hashlib.sha256(a.server.read_bytes()).hexdigest())};arrays={};files={}
            for dev,g in gen.items():
                packet=a.out/f'{case}-{seed}-{dev}.json';files[dev]=packet
                issue=g.transfer(packet);arrays[dev]=read(packet)
                if dev=='mps':assert arrays['cpu']==arrays['mps']
                name=dev+'-rust';dest=a.out/f'{case}-{seed}-{name}'
                cold=cli(a.runtime,program,dest,packet)
                reports[name]=audit_native(dest,base,True)
                reports[name].update(certificate=issue,cold_cli_ms=cold)
            no=a.out/f'{case}-{seed}-without-completion'
            cli(a.runtime,program,no,files['mps'],True);reports['rust-no-residual']=audit_native(no,base,False)
            separate=a.out/f'{case}-{seed}-cpu-without-completion'
            cli(a.runtime,program,separate,files['cpu'],True)
            assert audit_native(separate,base,False)==reports['rust-no-residual']
            assert read(separate/'events.json')==read(no/'events.json')
            blocked=a.out/f'{case}-{seed}-wrong.json';gen['cpu'].transfer(blocked,'wrong-parent')
            wrong=a.out/f'{case}-{seed}-wrong-native';cli(a.runtime,program,wrong,blocked)
            reports['rust-wrong-parent']=audit_native(wrong,base,True)
            assert reports['rust-wrong-parent']['children']==0
            def run_metal(dest,completion,bind=None):
                g=gen['mps'];fn=specialize(g.plan,g.emit,completion,False)
                fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,measure_resident=bind)
                if completion:verify(dest,metal_gold,image)
                report=read(dest/'run.json');roles=report['execution_roles']
                with np.load(dest/'output.npz') as z,np.load(metal_gold/'output.npz') as w:
                    first=next((i+1 for i,(s,v) in enumerate(zip(z['runs'],w['runs'])) if np.any(s!=v)),None)
                    return dict(runs=len(z['runs']),rhs=len(z['rhs']),children=roles['rhs_inputs_from_neural_port_claims'],
                                compiler_roots=roles['rhs_inputs_from_static_empty_lhs'],exact=roles['rhs_inputs_from_exact_search'],first_divergence=first)
            session={}
            def bind(infer,buf,*_):
                original={k:buf[k].clone() for k in ('state','meta','head','dyn','wm')}
                def reset():
                    for k,v in original.items():buf[k].copy_(v)
                    for k in ('regs','count','rhs','runs','writes','resumes'):buf[k].zero_()
                session.update(reset=reset,buf=buf,infer=infer)
            m=a.out/f'{case}-{seed}-metal'
            reports['mps-metal']=run_metal(m,True,bind)
            metal_no=a.out/f'{case}-{seed}-metal-without'
            reports['metal-no-residual']=run_metal(metal_no,False)
            for label,gpu_folder,rust_folder in [('assisted',m,a.out/f'{case}-{seed}-cpu-rust'),('no-residual',metal_no,no)]:
                ingress=image/'ingress.json'
                ordered=align(program,ingress,gpu_folder,rust_folder,rust_folder,initial_snapshot=initial_path)
                out=gpu_folder/'rust-ordered.json';out.write_text(json.dumps(ordered,separators=(',',':')))
                checked=endpoint(ingress,gpu_folder,rust_folder,out)
                assert checked['acceptance']=='pass',(case,seed,label,checked)
                reports['cross-'+label]=dict(acceptance=checked['acceptance'],runs=ordered['compared'],
                    aligned=ordered['aligned_by_ordinal'],typed_graph=checked['full_typed_graph_equal'])

            # Compare actual credited source ordinals using certificate slot ids across physical graph layouts.
            with np.load(m/'forest.npz') as z:metal_ord={i:int(v) for i,v in enumerate(z['children'][:,2]) if v}
            native=read(a.out/f'{case}-{seed}-cpu-rust'/'report.json')['precomputed_forest']
            rust_ord={v[0]:v[4] for v in native['children']}
            reports['origins']=dict(same_source_rhs=sum(metal_ord.get(i)==r for i,r in rust_ord.items()),
                only_native=sorted(rust_ord.keys()-metal_ord.keys()),only_metal=sorted(metal_ord.keys()-rust_ord.keys()),
                different_ordinal=sorted(i for i in rust_ord.keys()&metal_ord.keys() if rust_ord[i]!=metal_ord[i]))
            layout=a.out/f'{case}-{seed}-layout.json'
            static={k:v for k,v in arrays['cpu'].items() if k!='children'};layout.write_text(json.dumps(static,separators=(',',':')))
            proc=subprocess.Popen([str(a.server),str(program),str(layout)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            order=['cpu-rust','mps-rust','mps-metal']
            for arm in order:reports[arm]['timings']=[]
            with np.load(metal_gold/'output.npz') as z:gold={k:z[k] for k in ('rhs','runs','resumes','writes')}
            checksum=None
            try:
                for trial in range(6):
                    seq=order[trial%3:]+order[:trial%3]
                    for arm in seq if trial<3 else seq[::-1]:
                        if arm=='mps-metal':
                            session['reset']();torch.mps.synchronize();start=perf_counter_ns();session['infer']();torch.mps.synchronize()
                            ms=(perf_counter_ns()-start)/1e6
                            buf=session['buf'];st=buf['state'].cpu().tolist();assert st[7] and not st[5]
                            for k,i in [('rhs',9),('runs',11),('writes',10),('resumes',16)]:
                                h,w=buf[k][:st[i]].cpu().numpy(),gold[k]
                                if k=='rhs':np.testing.assert_array_equal(h[:,:2],w[:,:2]);h,w=h[:,4:],w[:,4:]
                                np.testing.assert_array_equal(h,w)
                            reports[arm]['timings'].append(dict(total_ms=ms));continue
                        if read_line(proc)!='ready':raise RuntimeError('native reset handshake')
                        dev=arm.split('-')[0];start=perf_counter_ns();_,tensor,_=gen[dev].emit()
                        if dev=='mps':torch.mps.synchronize()
                        after_forward=perf_counter_ns();words=tensor.cpu().numpy().tobytes();after_copy=perf_counter_ns()
                        send_words(proc,words);native_t=json.loads(read_line(proc));end=perf_counter_ns()
                        current=read_line(proc)
                        if checksum is None:
                            checksum=hashlib.sha256((base/'state.json').read_bytes()).hexdigest()

                        assert checksum==current and hashlib.sha256(words).hexdigest()==reports[arm]['certificate']['sha256']
                        assert native_t['children']==reports[arm]['children'] and native_t['rhs']==reports[arm]['rhs']
                        reports[arm]['timings'].append(dict(total_ms=(end-start)/1e6,forward_ms=(after_forward-start)/1e6,
                            copy_and_pack_ms=(after_copy-after_forward)/1e6,**native_t))
                assert read_line(proc)=='ready';send_words(proc,b'')
                if proc.wait()!=0:raise RuntimeError(proc.stderr.read().decode())
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
            for arm in order:reports[arm]['median_ms']=median(x['total_ms'] for x in reports[arm]['timings'])
            result[f'{case}/{seed}']=reports
            (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
            print(case,seed,[(arm,reports[arm]['children'],round(reports[arm]['median_ms'])) for arm in order],reports['origins'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','weights','runtime','server','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():study(p.parse_args())
