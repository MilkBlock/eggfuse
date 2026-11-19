"""Execute on MPS. This process accepts only the Cell packet and frozen pointer weights."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from importlib.util import module_from_spec,spec_from_file_location
from time import perf_counter_ns

import numpy as np
import torch

from ports import apply_roles
HERE=Path(__file__).resolve().parent
_spec=spec_from_file_location('pass3_address',HERE.parent/'multi-row-generation/address_ablation/model.py')
_address=module_from_spec(_spec);_spec.loader.exec_module(_address)
AddressModel=_address.AddressModel


def pointer(weight,n,dev):
    m=AddressModel('packed')
    m.load_state_dict(torch.load(weight,map_location='cpu',weights_only=True))
    m=m.eval().to(dev)
    length=(n+1)//2
    logical=torch.arange(n,device=dev)
    coords=torch.stack((logical//length,logical%length,logical*0),-1)
    # Physical placement is deliberately different from the logical address.
    physical=torch.as_tensor(np.random.default_rng(181).permutation(n),device=dev)
    scores=m.address_scores('make',coords[None],coords[physical][None],length,1)
    return physical,scores.argmax(-1)[0]


@torch.inference_mode()
def execute(packet,weight,port_weights,steps,lanes,root,capture=False,reader='learned'):
    if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0' or not torch.backends.mps.is_available():
        raise RuntimeError('Metal GPU required')
    if steps<0 or steps>4096:raise ValueError('Run budget outside trace capacity')
    start=perf_counter_ns();p=json.loads(packet.read_text())
    if p['schema']!='eggfuse.gpu-ingress/1':raise ValueError('expected offline device manifest')
    image_path=packet.with_name('device.npz')
    if hashlib.sha256(image_path.read_bytes()).hexdigest()!=p['device_sha256']:raise ValueError('image digest differs')
    with np.load(image_path,allow_pickle=False) as f:image=dict(f)
    layout,sets,strings=p['layout'],p['sets'],p['strings']
    rom,lits=image['rom'],image['lits']
    dev=torch.device('mps')
    limits=dict(ROW_CAP=16384,TOKEN_CAP=256,TRACE_CAP=65536,SEARCH_CAP=3000000,TOKEN_WIDTH=layout['NINPUT']+1)
    constants='\n'.join(f'#define {k} {v}' for k,v in {**layout,**limits}.items())
    lib=torch.mps.compile_shader(constants+'\n'+(HERE/'executor.metal').read_text())
    def ints(v):return torch.tensor(v,dtype=torch.int32,device=dev)
    def zeros(n,t=torch.int32):return torch.zeros(n,device=dev,dtype=t)
    prog=ints(rom);literal=torch.tensor(lits,device=dev,dtype=torch.int64)
    state=zeros(13);regs=zeros(layout['REGS']);meta=zeros((limits['ROW_CAP']+(2*(limits['ROW_CAP']+layout['NSYMBOLS']+2)+5)//6,6));head=zeros(layout['TABLES'])
    dyn=zeros((limits['ROW_CAP'],layout['WIDTH']),torch.int64);wm=zeros(layout['RULES'])-1
    count=zeros((layout['RULES'],2));tokens=zeros((layout['RULES'],2,limits['TOKEN_CAP'],limits['TOKEN_WIDTH']),torch.int64)
    rhs=zeros((limits['TRACE_CAP'],layout['NINPUT']+4),torch.int64)
    writes=zeros((limits['TRACE_CAP'],layout['WIDTH']+5),torch.int64);runs=zeros((max(1,steps),6))
    order=zeros(layout['NINST'])
    if reader=='learned':
        prog,valid=apply_roles(prog,image,port_weights,dev,layout['WIDTH'])
        physical,reads=pointer(weight,layout['NINST'],dev)
    else:
        physical=torch.as_tensor(np.random.default_rng(181).permutation(layout['NINST']),device=dev)
        reads=physical.argsort();valid=torch.tensor(True,device=dev)
    n=layout['NINST'];start_at=layout['INSTANCE']
    headers=prog[start_at:start_at+3*n].reshape(n,3)[physical]
    indices=torch.arange(3*n,device=dev)+start_at
    prog=prog.scatter(0,indices,headers[reads].reshape(-1))
    selected=physical[reads]
    selected=torch.where(valid & (selected==torch.arange(n,device=dev)),selected,-1).int().contiguous()
    lib.inject(prog,selected,state,meta,head,order,threads=1)
    torch.mps.synchronize();after_init=perf_counter_ns()
    width=p['max_set']*lanes
    if capture and steps>64:raise ValueError('prefix trace capacity is 64 Runs')
    snapshots=[]
    def observe():
        bank=torch.empty((1024,layout['WIDTH']),device=dev,dtype=torch.int64)
        lib.export_rows(prog,literal,state,meta,dyn,bank,threads=1024)
        uf=meta.view(-1)[6*limits['ROW_CAP']:6*limits['ROW_CAP']+limits['ROW_CAP']+layout['NSYMBOLS']+2]
        snapshots.append((bank,meta[:1024].clone(),state.clone(),uf.clone()))
    if capture:observe()
    for _ in range(steps):
        lib.next_run(prog,state,regs,threads=1)
        lib.search(prog,literal,state,meta,dyn,head,wm,count,tokens,lanes,threads=width,arg_casts={9:'int32'})
        lib.commit(prog,literal,state,meta,dyn,head,wm,count,tokens,rhs,writes,runs,lanes,threads=1,arg_casts={12:'int32'})
        if capture:observe()
    torch.mps.synchronize();after_exec=perf_counter_ns()
    out=torch.empty_like(dyn)
    lib.export_rows(prog,literal,state,meta,dyn,out,threads=limits['ROW_CAP'])
    torch.mps.synchronize()
    st=state.cpu().tolist();n=st[0]
    root.mkdir(parents=True,exist_ok=True)
    def take(t,stop):return t[:stop].cpu().numpy()
    np.savez_compressed(root/'output.npz',rows=take(out,n),meta=take(meta,n),rhs=take(rhs,st[9]),writes=take(writes,st[10]),
                        runs=take(runs,st[11]),parents=meta.view(-1)[6*limits['ROW_CAP']:6*limits['ROW_CAP']+n+layout['NSYMBOLS']+2].cpu().numpy(),
                        selected=selected.cpu().numpy())
    if capture:
        frames={}
        for j,(bank,m,st_dev,uf) in enumerate(snapshots):
            s=st_dev.cpu().tolist()
            if s[5]:break
            if s[0]>len(bank):raise ValueError('audit snapshot too small')
            frames[f'rows_{j}']=take(bank,s[0]);frames[f'meta_{j}']=take(m,s[0]);frames[f'parents_{j}']=take(uf,s[0]+layout['NSYMBOLS']+2)
        np.savez_compressed(root/'snapshots.npz',**frames)
    record=dict(reader=reader,port_weight_sha256=hashlib.sha256(port_weights.read_bytes()).hexdigest(),capture=capture,packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest(),weight_sha256=hashlib.sha256(weight.read_bytes()).hexdigest(),
                lanes=lanes,requested=steps,state=st,finished=bool(st[7]) and not st[5],completed=st[11],fault=st[5],
                fault_rule=st[6] if st[5] else None,sets=sets,strings=strings,
                setup_ms=(after_init-start)/1e6,inference_ms=(after_exec-after_init)/1e6,
                total_ms=(perf_counter_ns()-start)/1e6)
    (root/'run.json').write_text(json.dumps(record,indent=1)+'\n')
    print({k:record[k] for k in ('lanes','completed','fault','fault_rule','finished')},flush=True)
    if st[5]:raise SystemExit(2)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('packet',type=Path);parser.add_argument('weight',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--runs',type=int,default=2048);parser.add_argument('--rows',type=int,choices=(1,2),default=2)
    parser.add_argument('--capture-prefix',action='store_true')
    parser.add_argument('--port-weights',required=True,type=Path)
    parser.add_argument('--reader',choices=('exact','learned'),default='learned')
    a=parser.parse_args();execute(a.packet,a.weight,a.port_weights,a.runs,a.rows,a.output,a.capture_prefix,a.reader)
