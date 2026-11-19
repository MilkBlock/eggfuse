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


def pointer(weight,physical,dev):
    n=len(physical)
    m=AddressModel('packed')
    m.load_state_dict(torch.load(weight,map_location='cpu',weights_only=True))
    m=m.eval().to(dev)
    length=(n+1)//2
    logical=torch.arange(n,device=dev)
    coords=torch.stack((logical//length,logical%length,logical*0),-1)
    # Physical placement is deliberately different from the logical address.
    scores=m.address_scores('make',coords[None],coords[physical][None],length,1)
    return physical,scores.argmax(-1)[0]


@torch.inference_mode()
def execute(packet,weight,port_weights,steps,lanes,root,capture=False,reader='learned',union='fenced',directory='published',spine=True,lookup='hash',batch_runs=0,tiles=32,token_layout='packed',arena='shared',router=None,export_only=False,token_cap=256,scalars='integer',profile_prims=False,prune=False,row_audit=False):
    if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0' or not torch.backends.mps.is_available():
        raise RuntimeError('Metal GPU required')
    if steps<0 or steps>4096:raise ValueError('Run budget outside trace capacity')
    if lookup not in ('scan','point','hash') or batch_runs<0 or batch_runs>32:raise ValueError('lookup or batch budget')
    if lookup=='hash' and directory!='published':raise ValueError('hash keys require published-key storage')
    if batch_runs and capture:raise ValueError('use split dispatch to capture every Run')
    start=perf_counter_ns();p=json.loads(packet.read_text())
    if p['schema']!='eggfuse.gpu-ingress/1':raise ValueError('expected offline device manifest')
    image_path=packet.with_name('device.npz')
    if hashlib.sha256(image_path.read_bytes()).hexdigest()!=p['device_sha256']:raise ValueError('image digest differs')
    with np.load(image_path,allow_pickle=False) as f:image=dict(f)
    layout,sets,strings=p['layout'],p['sets'],p['strings']
    rom,lits=image['rom'],image['lits']
    dev=torch.device('mps')
    if router and lanes!=2:raise ValueError('trained router requires two rows')
    limits = dict(
        AUDIT_ROWS=int(row_audit), RUN_CAP=max(steps, 1), PRUNE_ROUTED=int(prune),
        SCALAR_MODE=('integer', 'guarded', 'lossy').index(scalars), PROFILE_PRIMS=int(profile_prims),
        LEARN_OWNER=int(router is not None), ROUTER=len(rom), SHARED_ARENA=int(arena=='shared'),
        PACK_TOKENS=int(token_layout=='packed'), TILES=tiles, PARTS=lanes*tiles,
        USE_POINTS=int(lookup!='scan'), USE_INDEX=int(lookup=='hash'), SPINE_ON=int(spine),
        PUBLISHED_KEYS=int(directory=='published'), FENCE_UNIONS=int(union=='fenced'),
        ROW_CAP=16384, TOKEN_CAP=token_cap, TRACE_CAP=65536, SEARCH_CAP=3000000,
        TOKEN_WIDTH=layout['NINPUT']+5,
    )
    constants='\n'.join(f'#define {k} {v}' for k,v in {**layout,**limits}.items())
    lib=torch.mps.compile_shader(constants+'\n'+(HERE/'executor.metal').read_text())
    def ints(v):return torch.tensor(v,dtype=torch.int32,device=dev)
    def zeros(n,t=torch.int32):return torch.zeros(n,device=dev,dtype=t)
    prog=ints(rom);literal=torch.tensor(lits,device=dev,dtype=torch.int64)
    cap=limits['ROW_CAP'];uf_size=cap+layout['NSYMBOLS']+2
    union_log=6*cap+2*uf_size+2*limits['TRACE_CAP']
    birth_run=union_log+4*uf_size
    state=zeros(51);regs=zeros(layout['REGS'])
    meta=zeros(((birth_run+(10*cap if router else 9*cap if tiles>1 else (6*cap+(2*cap if lookup=='hash' else 0)))+5)//6,6));head=zeros(layout['TABLES']*((257 if lookup=='hash' else 1)+(lanes*tiles if tiles>1 or router else 0)))
    dyn=zeros((cap*(2 if directory=='published' else 1),layout['WIDTH']),torch.int64);wm=zeros(layout['RULES'])-1
    banks=2 if arena=='shared' else lanes*tiles
    count=zeros((layout['RULES'],banks));cols=layout['TOTAL_TOKEN_COLS'] if token_layout=='packed' else layout['RULES']*limits['TOKEN_WIDTH']
    tokens=zeros(cols*banks*limits['TOKEN_CAP'],torch.int64)
    rhs=zeros((limits['TRACE_CAP'],layout['NINPUT']+4),torch.int64)
    writes=zeros((limits['TRACE_CAP'],layout['WIDTH']+7),torch.int64);runs=zeros((max(1,steps)*(2 if row_audit else 1),6))
    resumes=zeros((limits['TRACE_CAP'],6));order=zeros(layout['NINST'])
    physical=torch.as_tensor(image['physical_order'],device=dev).long()
    if reader=='learned':
        prog,valid=apply_roles(prog,image,port_weights,dev,layout['WIDTH'])
        physical,reads=pointer(weight,physical,dev)
    else:
        reads=physical.argsort();valid=torch.tensor(True,device=dev)
    n=layout['NINST'];start_at=layout['INSTANCE']
    headers=prog[start_at:start_at+3*n].reshape(n,3)[physical]
    indices=torch.arange(3*n,device=dev)+start_at
    prog=prog.scatter(0,indices,headers[reads].reshape(-1))
    selected=physical[reads]
    selected=torch.where(valid & (selected==torch.arange(n,device=dev)),selected,-1).int().contiguous()
    if router:
        from routing import assignments
        prog=torch.cat((prog,assignments(router,dev)))
    lib.inject(prog,selected,state,meta,head,order,literal,dyn,threads=1)
    if directory=='published':lib.seed_keys(prog,literal,state,meta,dyn,threads=len(image['members']))
    if lookup=='hash':lib.seed_index(prog,meta,dyn,head,threads=layout['TABLES'])
    torch.mps.synchronize();after_init=perf_counter_ns()
    width=p['max_set']*lanes*tiles
    if capture and steps>64:raise ValueError('prefix trace capacity is 64 Runs')
    snapshots=[]
    def observe():
        bank=torch.empty((1024,layout['WIDTH']),device=dev,dtype=torch.int64)
        lib.export_rows(prog,literal,state,meta,dyn,bank,threads=1024)
        uf=meta.view(-1)[6*limits['ROW_CAP']:6*limits['ROW_CAP']+limits['ROW_CAP']+layout['NSYMBOLS']+2]
        snapshots.append((bank,meta[:1024].clone(),state.clone(),uf.clone()))
    if capture:observe()
    if batch_runs:
        for base in range(0,steps,batch_runs):
            lib.run_batch(prog,literal,state,regs,meta,dyn,head,wm,count,tokens,rhs,writes,runs,resumes,
                          lanes,min(steps-base,batch_runs),threads=32,group_size=32,arg_casts={14:'int32',15:'int32'})
    else:
        for _ in range(steps):
            if arena=='shared':count.zero_()
            lib.next_run(prog,state,regs,count,threads=1)
            lib.search(prog,literal,state,meta,dyn,head,wm,count,tokens,lanes,threads=width,arg_casts={9:'int32'})
            lib.commit(prog,literal,state,meta,dyn,head,wm,count,tokens,rhs,writes,runs,resumes,lanes,threads=1,arg_casts={13:'int32'})
            if capture:observe()
    torch.mps.synchronize();after_exec=perf_counter_ns()
    out=torch.empty_like(dyn)
    lib.export_rows(prog,literal,state,meta,dyn,out,threads=limits['ROW_CAP'])
    torch.mps.synchronize()
    st=state.cpu().tolist();n=st[0]
    root.mkdir(parents=True,exist_ok=True)
    def take(t,stop):return t[:stop].cpu().numpy()
    if export_only:
        from export_graph import export
        schema_path=packet.with_name('export-schema.json')
        if hashlib.sha256(schema_path.read_bytes()).hexdigest()!=p['export_schema_sha256']:
            raise ValueError('export schema digest differs')
        schema=json.loads(schema_path.read_text())
        ids=zeros(uf_size);lib.export_roots(meta,ids,threads=uf_size)
        logical=export(schema,schema['tables'],take(out,n),take(meta,n),ids.cpu().numpy(),strings)
        (root/'state.json').write_text(json.dumps(logical,ensure_ascii=False,separators=(',',':')))
    else:
        np.savez_compressed(root/'output.npz',rows=take(out,n),meta=take(meta,n),rhs=take(rhs,st[9]),writes=take(writes,st[10]),
                        runs=take(runs,st[11]),parents=meta.view(-1)[6*limits['ROW_CAP']:6*limits['ROW_CAP']+n+layout['NSYMBOLS']+2].cpu().numpy(),
                        birth_runs=meta.view(-1)[birth_run:birth_run+n].cpu().numpy(),
                        birth_fields=take(dyn,n),
                        unions=meta.view(-1)[union_log:union_log+4*st[14]].reshape(-1,4).cpu().numpy(),
                        resumes=take(resumes,st[16]),contributions=take(runs[max(1,steps):],st[11]) if row_audit else np.empty((0,6),np.int32),selected=selected.cpu().numpy())
    if capture:
        frames={}
        for j,(bank,m,st_dev,uf) in enumerate(snapshots):
            s=st_dev.cpu().tolist()
            if s[5]:break
            if s[0]>len(bank):raise ValueError('audit snapshot too small')
            frames[f'rows_{j}']=take(bank,s[0]);frames[f'meta_{j}']=take(m,s[0]);frames[f'parents_{j}']=take(uf,s[0]+layout['NSYMBOLS']+2)
        np.savez_compressed(root/'snapshots.npz',**frames)
    record=dict(row_audit=row_audit,prune=prune,scalars=scalars,profile_prims=profile_prims,token_cap=token_cap,export_only=export_only,router=hashlib.sha256(router.read_bytes()).hexdigest() if router else None,arena=arena,token_layout=token_layout,token_bank_bytes=tokens.numel()*8,tiles=tiles,lookup=lookup,batch_runs=batch_runs,spine=spine,directory=directory,union=union,reader=reader,port_weight_sha256=hashlib.sha256(port_weights.read_bytes()).hexdigest(),capture=capture,packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest(),weight_sha256=hashlib.sha256(weight.read_bytes()).hexdigest(),
                lanes=lanes,requested=steps,state=st,finished=bool(st[7]) and not st[5],completed=st[11],fault=st[5],
                fault_rule=st[6] if st[5] else None,sets=sets,strings=strings,
                setup_ms=(after_init-start)/1e6,inference_ms=(after_exec-after_init)/1e6,
                total_ms=(perf_counter_ns()-start)/1e6)
    (root/'run.json').write_text(json.dumps(record,indent=1)+'\n')
    print({k:record[k] for k in ('lanes','completed','fault','fault_rule','finished')},flush=True)
    if st[5]:raise SystemExit(2)
    if export_only and not st[7]:raise SystemExit(3)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('packet',type=Path);parser.add_argument('weight',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--runs',type=int,default=2048);parser.add_argument('--rows',type=int,choices=(1,2),default=2)
    parser.add_argument('--capture-prefix',action='store_true')
    parser.add_argument('--port-weights',required=True,type=Path)
    parser.add_argument('--reader',choices=('exact','learned'),default='learned')
    parser.add_argument('--union',choices=('immediate','fenced'),default='fenced')
    parser.add_argument('--directory',choices=('canonical','published'),default='published')
    parser.add_argument('--spine',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--lookup',choices=('scan','point','hash'),default='hash')
    parser.add_argument('--batch-runs',type=int,default=0)
    parser.add_argument('--tiles',type=int,choices=(1,2,4,8,16,32,64),default=32)
    parser.add_argument('--token-layout',choices=('dense','packed'),default='packed')
    parser.add_argument('--arena',choices=('private','shared'),default='shared')
    parser.add_argument('--router',type=Path,help='frozen shared row router weights')
    parser.add_argument('--export-only',action='store_true')
    parser.add_argument('--token-cap',type=int,choices=(32,64,128,256),default=256)
    parser.add_argument('--scalars',choices=('integer','guarded','lossy'),default='integer')
    parser.add_argument('--profile-prims',action='store_true')
    parser.add_argument('--prune-routed',action='store_true')
    parser.add_argument('--row-audit',action='store_true')
    a=parser.parse_args();execute(a.packet,a.weight,a.port_weights,a.runs,a.rows,a.output,a.capture_prefix,a.reader,a.union,a.directory,a.spine,a.lookup,a.batch_runs,a.tiles,a.token_layout,a.arena,a.router,a.export_only,a.token_cap,a.scalars,a.profile_prims,a.prune_routed,a.row_audit)
