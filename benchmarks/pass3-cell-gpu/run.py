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
def execute(packet,weight,port_weights,steps,lanes,root,capture=False,reader='learned',union='fenced',directory='published',spine=True,lookup='hash',batch_runs=0,tiles=32,token_layout='packed',arena='shared',router=None,export_only=False,token_cap=256,scalars='integer',profile_prims=False,prune=False,row_audit=False,measure_resident=None,hot_filter=4,index_repair=False,count_work=False,block_study=None,neural=None,maintenance_repeat=1,maintenance_control=False):
    if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0' or not torch.backends.mps.is_available():
        raise RuntimeError('Metal GPU required')
    if steps<0 or steps>4096:raise ValueError('Run budget outside trace capacity')
    if lookup not in ('scan','point','hash') or batch_runs<0 or batch_runs>32:raise ValueError('lookup or batch budget')
    if lookup=='hash' and directory!='published':raise ValueError('hash keys require published-key storage')
    if batch_runs and capture:raise ValueError('use split dispatch to capture every Run')
    if index_repair and (lookup!='hash' or directory!='published'):
        raise ValueError('indexed repair requires a published full-key index')
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
        COUNT_WORK=int(count_work), INDEX_REPAIR=int(index_repair), PHASE_TIMING=int(measure_resident is not None), HOT_FILTER=int(hot_filter), AUDIT_ROWS=int(row_audit), RUN_CAP=max(steps, 1), PRUNE_ROUTED=int(prune),
        SCALAR_MODE=('integer', 'guarded', 'lossy').index(scalars), PROFILE_PRIMS=int(profile_prims),
        LEARN_OWNER=int(router is not None), ROUTER=len(rom), SHARED_ARENA=int(arena=='shared'),
        PACK_TOKENS=int(token_layout=='packed'), TILES=tiles, PARTS=lanes*tiles,
        USE_POINTS=int(lookup!='scan'), USE_INDEX=int(lookup=='hash'), SPINE_ON=int(spine),
        PUBLISHED_KEYS=int(directory=='published'), FENCE_UNIONS=int(union=='fenced'),
        ROW_CAP=16384, TOKEN_CAP=token_cap, TRACE_CAP=65536, SEARCH_CAP=3000000,
        TOKEN_WIDTH=layout['NINPUT']+5,
    )
    sets_enabled=bool(layout.get('HAS_SETS'))
    set_base=6*limits['ROW_CAP']+6*(limits['ROW_CAP']+layout['NSYMBOLS']+2)+2*limits['TRACE_CAP']+10*limits['ROW_CAP']
    limits['SET_BASE']=set_base
    limits['BLOCK_BASE']=set_base+(126 if sets_enabled else 0)
    if maintenance_repeat<1:raise ValueError('invalid maintenance replay count')
    limits['SET_MAINT_REPEAT']=maintenance_repeat
    limits['SET_MAINT_CONTROL']=int(maintenance_control)
    if block_study and row_audit:raise ValueError("separate block-credit and row-contribution audits")
    if block_study:
        limits.update(BLOCK_STUDY=1,SELECT_BLOCKS=int(block_study['select']),INDEX_NOTIFY=int(block_study['notify']),
                      LIBRARY_SIZE=len(block_study['ids']))
    grouping=block_study.get('group') if block_study else None
    region=block_study.get('region') if block_study else None
    if region:
        if grouping:raise ValueError('independent region and co-repair trials')
        cap=limits['ROW_CAP'];budget=int(region['budget']);window=int(region['window'])
        if not 1<=budget<=cap//32 or window<1:raise ValueError('invalid region budget')
        region_base=limits['BLOCK_BASE']+3*cap+layout['TABLES']*lanes*tiles
        reg_payload=region_base+3*(cap//32)+2*budget
        reg_counter=88+3*len(block_study['ids'])+2*(1+max(block_study['shapes']))
        region_trace=region['capture']
        limits.update(REG_BASE=region_base,REG_BUDGET=budget,REG_WINDOW=window,REG_COUNTER=reg_counter,
                      REGION_CAPTURE=int(region_trace),REGION_SELECT=int(not region_trace),REGION_ORACLE=int('oracle' in region))
    if grouping:
        mode=grouping['mode'];trace=grouping.get('trace',False)
        if mode not in (1,2,3,4) or not block_study['notify'] or (trace and mode!=1):
            raise ValueError('invalid co-repair mode')
        edges=grouping['edges'];members=grouping['members']
        if members not in (1,2,3):raise ValueError('unsupported member limit')
        group_base=limits['BLOCK_BASE']+3*limits['ROW_CAP']+layout['TABLES']*lanes*tiles
        group_counter=88+3*len(block_study['ids'])+2*(1+max(block_study['shapes']))
        cap=limits['ROW_CAP']
        group_words=group_base if mode==1 else group_base+(7 if mode==3 else 3)*cap+cap//32
        dict_words=1+4*members*layout['WIDTH']
        solo=grouping.get('solo',False)
        if solo and mode!=3:raise ValueError('solo result variant requires port masks')
        if mode==3:group_words+=(cap if solo else cap//2)*dict_words
        limits.update(CO_SOLO=int(solo),CO_NESTED=int(grouping.get('nested',False)),CO_SPARSE_WORDS=int(grouping.get('sparse_words',False)),CO_MODE=mode,CO_MEMBERS=members,CO_BASE=group_base,CO_COUNTER=group_counter,
                      CO_LIBRARY=len(edges),CO_TRACE=int(trace),CO_DICT_WORDS=dict_words)
        if trace:
            limits.update(CO_FIELDS=group_words,CO_EDGES=group_words+cap*layout['WIDTH'],
                          CO_EVENTS=group_words+2*cap*layout['WIDTH'])
            group_words=limits['CO_EVENTS']+3*limits['TRACE_CAP']
    if neural is not None:
        if block_study or batch_runs or arena!='shared' or not spine:raise ValueError('neural proposer requires split, shared Spine executor')
        ranks=neural['ranks'];nr=neural['rows'];hidden=neural['hidden'];leaves=len(neural['catalog'])
        if min(ranks,nr,hidden,leaves)<1:raise ValueError('invalid neural dimensions')
        ncapture=neural.get('capture',False)
        waves=neural.get('waves',1)
        if not 1<=waves<=32:raise ValueError('unsupported number of verifier waves')
        stop_on_null=neural.get('stop_on_null',False)
        if stop_on_null and ncapture:raise ValueError('stopping requires an online actor')
        limits['NEURAL_STOP_NULL']=int(stop_on_null)
        bootstrap=neural.get('bootstrap_only',False)
        if bootstrap and (ncapture or neural.get('complete_residual',True)):
            raise ValueError('bootstrap control requires neural proposals with residual disabled')
        fusion=neural.get('fusion',0)
        if fusion not in (0,1,2) or (fusion and (ncapture or waves!=2 or nr!=2)):
            raise ValueError('fused exchange requires two waves of two rows')
        limits.update(NEURAL_BOOTSTRAP_ONLY=int(bootstrap),NEURAL_FUSE=fusion)
        per_run=nr*waves
        capture_receipts=ncapture and neural.get('receipt_labels',False)
        capture_edges=ncapture and neural.get('capture_edges',False)
        edge_base=limits['BLOCK_BASE']+limits['TRACE_CAP']+int(capture_receipts)*steps*leaves*ranks
        limits.update(NEURAL_EDGES=int(capture_edges),EDGE_BEFORE=edge_base,
                      EDGE_CONSUMED=edge_base+limits['ROW_CAP'],
                      EDGE_PUBLISHED=edge_base+limits['ROW_CAP']+limits['TRACE_CAP'])
        feedback=neural.get('feedback',0)
        if neural.get('receipt_head') and nr!=2:raise ValueError('receipt policy requires two rows')
        if feedback not in (0,1,2) or (feedback and not neural.get('receipt_head')):
            raise ValueError('invalid receipt visibility')
        limits.update(NEURAL_WAVES=waves,NEURAL_SLOTS=per_run,NEURAL_LABELS=int(capture_receipts),
                      NEURAL_FEEDBACK=feedback,NEURAL_RECEIPT_HEAD=int(neural.get('receipt_head',False)),
                      NEURAL_EXCLUDE_CLOSED=int(neural.get('exclude_closed', False)),
                      NEURAL_SHUFFLE=int(neural.get('shuffle_receipts',False)))
        nbase=limits['BLOCK_BASE']
        limits.update(NEURAL_ORDINAL=1,NEURAL_ACTIVE=int(not ncapture),NEURAL_CAPTURE=int(ncapture),NEURAL_BASE=nbase,
                      NEURAL_ROWS=nr,NEURAL_RANKS=ranks,NEURAL_LEAVES=leaves,NEURAL_ACTIONS=ranks*leaves,NEURAL_H=hidden,
                      NEURAL_CLOSE=int(neural.get('close',True)),NEURAL_SHADOW=int(neural.get('shadow',False)),NEURAL_INTERVENTION=neural.get('intervention',0))
    compound=neural.get('compound') if neural else None
    replay=compound.get('replay') if compound is not None else None
    host_actor=compound.get('host_actor') if compound is not None else None
    host_control=host_actor is not None or bool(compound and compound.get('host_control'))
    if host_actor is not None:
        if replay is not None or not compound['batch']:raise ValueError('CPU policy requires an online pending-parent batch')
        limits['COM_REPLAY_RUNS']=steps
    limits['HOST_CONTROL']=int(host_control)
    external_tokens=replay is not None or host_actor is not None
    if replay is not None:
        if replay.dtype!=np.float32 or replay.ndim!=3 or replay.shape[1:]!=(4,12) or not 0<len(replay)<=steps or not np.isfinite(replay).all():
            raise ValueError('invalid frozen compound token stream')
        limits['COM_REPLAY_RUNS']=len(replay)
    if compound is not None:
        if (waves,nr,hidden,ranks)!=(2,2,8,8) or fusion or ncapture or stop_on_null:
            raise ValueError('compound policy requires two waves of two online rows')
        joins=compound['joins']
        if not joins or any(len(j)!=4 or not 0<=j[1]<leaves or not 0<=j[3]<leaves or j[2]<0 for j in joins):
            raise ValueError('invalid compound policy joins')
        if len(compound['child'])!=24*len(joins)+18:
            raise ValueError('invalid compound policy weight size')
        records=nbase+(4+steps)*per_run
        queue=records+11*nr*steps
        limits.update(COMPOUND=1,COM_JOINS=len(joins),COM_BATCH=int(compound['batch']),
                      COM_MASK_PARENT=int(compound.get('mask_parent',False)),
                      COM_RECORDS=records,COM_QUEUE=queue,COM_HEAD=queue+nr*steps)
    if compound and compound.get('audit_claim_time'):
        limits['COM_FAILURE_RUN']=limits['COM_HEAD']+2*limits['ROW_CAP']
    constants='\n'.join(f'#define {k} {v}' for k,v in {**layout,**limits}.items())
    if block_study:
        for name,values in [('bake_entries',block_study['entries']),('repair_shapes',block_study['shapes']),('bake_pivots',block_study['pivots']),('bake_tables',block_study['tables'])]:
            constants+='\nconstant int '+name+'[]={'+','.join(map(str,values))+'};'
    shader=(HERE/'executor.metal').read_text()
    if region:
        coefs=region['weights']
        if len(coefs)!=6 or not all(np.isfinite(v) for v in [*coefs,region['bias'],region['build_price']]):
            raise ValueError('invalid region model')
        constants+='\nconstant float region_weights[]={'+','.join(str(float(n))+'f' for n in coefs)+'};'
        constants+='\nconstant float region_bias='+str(float(region['bias']))+'f;'
        constants+='\nconstant float region_build_price='+str(float(region['build_price']))+'f;'
        if 'oracle' in region:
            oracle=region['oracle']
            if len(oracle)!=(steps//window+1)*(cap//32//32):raise ValueError('invalid oracle window grid')
            constants+='\nconstant uint region_oracle[]={'+','.join(str(int(x))+'u' for x in oracle)+'};'
        shader=shader.replace('// REGION_DEVICE_FUNCTIONS',(HERE/'region-admission/policy.metal').read_text())
    if grouping:
        values=[str(int(v)) for edge in edges for v in edge] or ['-1']
        constants+='\nconstant int co_library[]={'+','.join(values)+'};'
        if grouping.get('nested') or solo:
            producers={r[0] for r in edges}
            constants+='\nconstant int co_producer_table[]={'+','.join(str(int(t in producers)) for t in range(layout['TABLES']))+'};'
        shader=shader.replace('// CO_REPAIR_DEVICE_FUNCTIONS',(HERE/'co-repair/owner.metal').read_text())
    if neural is not None:
        catalog=','.join(str(int(i)) for row in neural['catalog'] for i in row)
        constants+='\nconstant int neural_catalog[]={'+catalog+'};'
        if compound is not None:
            constants+='\nconstant int compound_joins[]={'+','.join(str(int(v)) for j in joins for v in j)+'};'
        module=HERE/'recurrent-generator'
        kernels=(module/'features.metal').read_text()
        if not ncapture:kernels+='\n'+(module/'actor.metal').read_text()
        if compound is not None:kernels+='\n'+(module/'compound.metal').read_text()
        if external_tokens:kernels+='\n'+(module/'compound_replay.metal').read_text()
        shader=shader.replace('// NEURAL_DEVICE_KERNELS',kernels)
    lib=torch.mps.compile_shader(constants+'\n'+shader)
    def ints(v):return torch.tensor(v,dtype=torch.int32,device=dev)
    def zeros(n,t=torch.int32):return torch.zeros(n,device=dev,dtype=t)
    prog=ints(rom);literal=torch.tensor(lits,device=dev,dtype=torch.int64)
    cap=limits['ROW_CAP'];uf_size=cap+layout['NSYMBOLS']+2
    union_log=6*cap+2*uf_size+2*limits['TRACE_CAP']
    birth_run=union_log+4*uf_size
    state=zeros(77 if compound is not None else 75 if neural is not None else reg_counter+7 if region else group_counter+16 if grouping else 88+3*len(block_study['ids'])+2*(1+max(block_study['shapes'])) if block_study else 69 if sets_enabled else 56);regs=zeros(layout['REGS'])
    meta_words=birth_run+(10*cap if router else 9*cap if tiles>1 else (6+2*int(lookup=='hash'))*cap)
    if sets_enabled:meta_words=set_base+126
    if neural is not None:
        meta_words=nbase+(limits['TRACE_CAP'] if ncapture else (4+steps)*per_run)
        if capture_receipts:meta_words+=steps*leaves*ranks
        if capture_edges:meta_words+=cap+5*limits['TRACE_CAP']
    if compound is not None:meta_words=limits['COM_HEAD']+2*cap
    if 'COM_FAILURE_RUN' in limits:meta_words+=steps*nr
    if block_study:meta_words=limits['BLOCK_BASE']+3*cap+layout["TABLES"]*lanes*tiles
    if region:
        region_windows=steps//window+1
        meta_words=reg_payload+(8*region_windows*(cap//32) if region_trace else (region_windows*(cap//32//32) if count_work else 0))
    if grouping:meta_words=group_words
    meta=zeros(((meta_words+5)//6,6))
    head_words=(257 if lookup=='hash' else 1)+(lanes*tiles if tiles>1 or router else 0)
    head_words+=int(hot_filter>0)+(lanes*tiles if hot_filter in (2,3) else 0)
    head_size=layout['TABLES']*head_words
    if block_study and block_study['notify']:
        head_size+=(2*(cap//32)+2*uf_size*budget) if region else (cap//32)*(uf_size+2)
    if grouping and grouping.get('sparse_words'):
        head_size+=uf_size*((cap//32+31)//32)
    head=zeros(head_size)
    dyn=zeros((cap*(2 if directory=='published' else 1),layout['WIDTH']),torch.int64);wm=zeros(layout['RULES'])-1
    banks=2 if arena=='shared' else lanes*tiles
    count=zeros((layout['RULES'],banks));cols=layout['TOTAL_TOKEN_COLS'] if token_layout=='packed' else layout['RULES']*limits['TOKEN_WIDTH']
    tokens=zeros(cols*banks*limits['TOKEN_CAP'],torch.int64)
    rhs=zeros((limits['TRACE_CAP'],layout['NINPUT']+4),torch.int64)
    writes=zeros((limits['TRACE_CAP'],layout['WIDTH']+7),torch.int64);runs=zeros((max(1,steps)*(2 if row_audit or block_study else 1),6))
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
    if neural is not None:
        feats=zeros((steps if ncapture else 1,leaves*ranks,8))
        if not ncapture:
            # Both banks stay on device. Only the initial neural frontier is seeded.
            frontier=torch.zeros((2,nr,hidden+4),device=dev,dtype=torch.float32)
            policy=torch.tensor(neural['weights'],device=dev,dtype=torch.float32)
            raw_trace=torch.zeros((steps,per_run,hidden+4),device=dev,dtype=torch.float32)
            verdict=zeros((steps,per_run,4))
            if compound is not None:child_weights=torch.tensor(compound['child'],device=dev,dtype=torch.float32)
    if replay is not None:
        frozen=torch.tensor(replay,device=dev,dtype=torch.float32).contiguous()
    if host_actor is not None:frozen=raw_trace
    def infer():
        if host_actor is not None:host_actor.reset()
        if batch_runs:
            for base in range(0,steps,batch_runs):
                lib.run_batch(prog,literal,state,regs,meta,dyn,head,wm,count,tokens,rhs,writes,runs,resumes,
                              lanes,min(steps-base,batch_runs),threads=32,group_size=32,arg_casts={14:'int32',15:'int32'})
        else:
            for iteration in range(steps):
                if arena=='shared':count.zero_()
                lib.next_run(prog,state,regs,count,threads=1)
                if neural is not None:
                    if capture_edges:
                        lib.neural_snapshot_anchors(state,meta,threads=cap)
                    if fusion!=2:
                        lib.neural_features(prog,state,meta,head,wm,feats,threads=leaves*ranks)
                    if compound is not None:
                        if host_control:
                            observed=feats.cpu()
                            if observed[0,0,1].item()<0:break
                            if host_actor is not None:
                                raw_trace[iteration].copy_(host_actor.emit(observed,iteration+1))
                        parent,children=frontier[1],frontier[0]
                        if not external_tokens:
                            lib.neural_propose(state,feats,policy,children,parent,raw_trace,verdict,0,
                                               threads=nr,arg_casts={7:'int32'})
                        else:
                            lib.frozen_compound_wave(state,meta,frozen,parent,raw_trace,0,threads=1,arg_casts={5:'int32'})
                        if compound['batch']:
                            if not external_tokens:
                                lib.compound_child(state,meta,child_weights,parent,children,raw_trace,verdict,threads=nr)
                            else:
                                lib.frozen_compound_wave(state,meta,frozen,children,raw_trace,1,threads=1,arg_casts={5:'int32'})
                        lib.neural_verify(prog,literal,state,meta,dyn,head,wm,count,tokens,parent,verdict,0,
                                          threads=1,arg_casts={11:'int32'})
                        if not compound['batch']:
                            if not external_tokens:
                                lib.compound_child(state,meta,child_weights,parent,children,raw_trace,verdict,threads=nr)
                            else:
                                lib.frozen_compound_wave(state,meta,frozen,children,raw_trace,1,threads=1,arg_casts={5:'int32'})
                        lib.compound_resume(prog,literal,state,meta,dyn,head,wm,count,tokens,threads=1)
                    elif fusion:
                        lib.neural_exchange(prog,literal,state,meta,dyn,head,wm,count,tokens,feats,policy,
                                            frontier,raw_trace,verdict,threads=32,group_size=32)
                    elif not ncapture:
                        for wave in range(waves):
                            tick=iteration*waves+wave
                            previous=frontier[tick%2];current=frontier[1-tick%2]
                            lib.neural_propose(state,feats,policy,previous,current,raw_trace,verdict,wave,
                                               threads=nr,arg_casts={7:'int32'})
                            lib.neural_verify(prog,literal,state,meta,dyn,head,wm,count,tokens,current,verdict,wave,
                                              threads=1,arg_casts={11:'int32'})
                if neural is None or neural.get('complete_residual',True) or bootstrap:
                    lib.search(prog,literal,state,meta,dyn,head,wm,count,tokens,lanes,threads=width,arg_casts={9:'int32'})
                lib.commit(prog,literal,state,meta,dyn,head,wm,count,tokens,rhs,writes,runs,resumes,lanes,threads=1,arg_casts={13:'int32'})
                if capture:observe()
    if measure_resident is not None:
        buffers=dict(prog=prog,literal=literal,state=state,regs=regs,meta=meta,dyn=dyn,head=head,
                     wm=wm,count=count,tokens=tokens,rhs=rhs,writes=writes,runs=runs,resumes=resumes)
        if neural is not None and not ncapture:
            buffers.update(frontier=frontier,raw_trace=raw_trace,verdict=verdict)
        measure_resident(infer,buffers,constants,width,steps,lanes)
        after_init=perf_counter_ns()
    infer()
    torch.mps.synchronize();after_exec=perf_counter_ns()
    out=torch.empty_like(dyn)
    lib.export_rows(prog,literal,state,meta,dyn,out,threads=limits['ROW_CAP'])
    torch.mps.synchronize()
    st=state.cpu().tolist();n=st[0]
    root.mkdir(parents=True,exist_ok=True)
    def take(t,stop):return t[:stop].cpu().numpy()
    set_members=meta.view(-1)[set_base:set_base+63].cpu().numpy() if sets_enabled else np.empty(0,np.int32)
    if region and region_trace and not st[5]:
        mem=meta.view(-1)
        records=mem[reg_payload:].cpu().numpy()[:8*region_windows*(cap//32)]
        np.savez_compressed(root/'regions.npz',windows=records.reshape(region_windows,cap//32,8)[:(st[11]+window-1)//window])
    if region and not region_trace and count_work and not st[5]:
        mem=meta.view(-1)
        selected_windows=mem[reg_payload:reg_payload+region_windows*(cap//32//32)].cpu().numpy().reshape(region_windows,-1)
        np.savez_compressed(root/'selected.npz',words=selected_windows)
    if grouping and count_work and mode>=2 and not st[5]:
        mem=meta.view(-1)
        np.savez_compressed(root/'owners.npz',
            owner=mem[group_base:group_base+n].cpu().numpy(),
            first=mem[group_base+cap:group_base+cap+n].cpu().numpy(),
            second=mem[group_base+2*cap:group_base+2*cap+n].cpu().numpy())
    if neural is not None:
        if ncapture:
            extra={}
            if capture_edges:
                mem=meta.view(-1)
                if st[17]>limits['TRACE_CAP']:raise ValueError('anchor publication log overflow')
                offset=limits['EDGE_PUBLISHED']
                extra['publications']=mem[offset:offset+4*st[17]].reshape(-1,4).cpu().numpy()
                offset=limits['EDGE_CONSUMED']
                extra['consumed']=mem[offset:offset+st[9]].cpu().numpy()
            if capture_receipts:
                offset=nbase+limits['TRACE_CAP']
                extra['receipt']=meta.view(-1)[offset:offset+st[11]*leaves*ranks].reshape(st[11],leaves*ranks).cpu().numpy()
            np.savez_compressed(root/'neural-inputs.npz',**extra,features=feats[:st[11]].cpu().numpy(),
                                pivot=meta.view(-1)[nbase:nbase+st[9]].cpu().numpy())
        else:
            flags=meta.view(-1)[nbase+4*per_run:nbase+(4+st[11])*per_run].reshape(-1,per_run)
            neural_wins=int((flags!=0).sum().item())
            if compound is not None:
                offset=limits['COM_RECORDS']
                claims=meta.view(-1)[offset:offset+st[11]*nr*11].reshape(st[11],nr,11).cpu().numpy()
                if 'COM_FAILURE_RUN' in limits:
                    failure_offset=limits['COM_FAILURE_RUN']
                    failure_run=meta.view(-1)[failure_offset:failure_offset+st[11]*nr].reshape(st[11],nr).cpu().numpy()
                    np.savez_compressed(root/'claim-failure-times.npz',failure_run=failure_run)
                np.savez_compressed(root/'compound-output.npz',claims=claims)
                child_wins=int((claims[:,:,7]>0).sum())
                neural_wins+=child_wins
            np.savez_compressed(root/'neural-output.npz',raw=raw_trace[:st[11]].cpu().numpy(),
                                verdict=verdict[:st[11]].cpu().numpy(),committed=(flags!=0).cpu().numpy(),
                                rhs_ordinal=flags.cpu().numpy())
    if grouping and trace:
        mem=meta.view(-1)
        logged=st[group_counter+12]
        if not st[5] and logged<=limits['TRACE_CAP']:
            edges_out=mem[limits['CO_EDGES']:limits['CO_EDGES']+n*layout['WIDTH']].reshape(n,-1)
            events=mem[limits['CO_EVENTS']:limits['CO_EVENTS']+3*logged].reshape(-1,3)
            np.savez_compressed(root/'co-repair.npz',edges=edges_out.cpu().numpy(),events=events.cpu().numpy())
    if export_only:
        from export_graph import export
        schema_path=packet.with_name('export-schema.json')
        if hashlib.sha256(schema_path.read_bytes()).hexdigest()!=p['export_schema_sha256']:
            raise ValueError('export schema digest differs')
        schema=json.loads(schema_path.read_text())
        ids=zeros(uf_size);lib.export_roots(meta,ids,threads=uf_size)
        logical=export(schema,schema['tables'],take(out,n),take(meta,n),ids.cpu().numpy(),strings,set_members)
        (root/'state.json').write_text(json.dumps(logical,ensure_ascii=False,separators=(',',':')))
    else:
        np.savez_compressed(root/'output.npz',set_members=set_members,rows=take(out,n),meta=take(meta,n),rhs=take(rhs,st[9]),writes=take(writes,st[10]),
                        runs=take(runs,st[11]),parents=meta.view(-1)[6*limits['ROW_CAP']:6*limits['ROW_CAP']+n+layout['NSYMBOLS']+2].cpu().numpy(),
                        birth_runs=meta.view(-1)[birth_run:birth_run+n].cpu().numpy(),
                        birth_fields=take(dyn,n),
                        unions=meta.view(-1)[union_log:union_log+4*st[14]].reshape(-1,4).cpu().numpy(),
                        resumes=take(resumes,st[16]),block_coverage=take(runs[max(1,steps):],st[11]) if block_study else np.empty((0,6),np.int32),contributions=take(runs[max(1,steps):],st[11]) if row_audit else np.empty((0,6),np.int32),selected=selected.cpu().numpy())
    if capture:
        frames={}
        for j,(bank,m,st_dev,uf) in enumerate(snapshots):
            s=st_dev.cpu().tolist()
            if s[5]:break
            if s[0]>len(bank):raise ValueError('audit snapshot too small')
            frames[f'rows_{j}']=take(bank,s[0]);frames[f'meta_{j}']=take(m,s[0]);frames[f'parents_{j}']=take(uf,s[0]+layout['NSYMBOLS']+2)
        np.savez_compressed(root/'snapshots.npz',**frames)
    record=dict(entry_clock_ns=start,count_work=count_work,index_repair=index_repair,hot_filter=hot_filter,row_audit=row_audit,prune=prune,scalars=scalars,profile_prims=profile_prims,token_cap=token_cap,export_only=export_only,router=hashlib.sha256(router.read_bytes()).hexdigest() if router else None,arena=arena,token_layout=token_layout,token_bank_bytes=tokens.numel()*8,tiles=tiles,lookup=lookup,batch_runs=batch_runs,spine=spine,directory=directory,union=union,reader=reader,port_weight_sha256=hashlib.sha256(port_weights.read_bytes()).hexdigest(),capture=capture,packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest(),weight_sha256=hashlib.sha256(weight.read_bytes()).hexdigest(),
                lanes=lanes,requested=steps,state=st,finished=bool(st[7]) and not st[5],completed=st[11],fault=st[5],
                fault_rule=st[6] if st[5] else None,sets=sets,strings=strings,
                setup_ms=(after_init-start)/1e6,inference_ms=(after_exec-after_init)/1e6,
                total_ms=(perf_counter_ns()-start)/1e6)
    if region:
        record['region']=dict(budget=budget,window=window,counters=st[reg_counter:],
                              index_bytes=(meta_words-region_base+head_size-layout['TABLES']*head_words)*4)
    if grouping:
        record['co_repair']=dict(mode=mode,members=members,counters=st[group_counter:],
                                 extra_meta_bytes=(group_words-group_base)*4,
                                 extra_summary_bytes=uf_size*((cap//32+31)//32)*4 if grouping.get('sparse_words') else 0)
    record['execution_roles'] = {
        'binding_generator': 'exact_metal_search',
        'rhs_inputs_from_exact_search': st[9],
        'rhs_inputs_from_recurrent_neural_proposals': 0,
        'next_run_state': 'committed_device_graph_indexes_and_spine',
        'recurrent_neural_token_input': False,
        'ingress_reader': reader,
        'learned_entry_router': router is not None,
    }
    if neural is not None and not ncapture:
        record['neural_work_counts']=dict(zip(('exact_seeds_skipped','verified_steps','remaining_route_steps',
                                               'verifier_point_reads','remaining_route_point_reads'),st[69:74]))
        residual=neural.get('complete_residual',True)
        if not (residual or bootstrap) and st[9]!=neural_wins:raise ValueError('unattributed RHS in neural-only control')
        record['execution_roles'].update(binding_generator='recurrent_neural_proposals_and_exact_metal_completion' if residual else ('recurrent_neural_proposals_and_exact_empty_lhs' if bootstrap else 'recurrent_neural_proposals_only'),
            rhs_inputs_from_exact_search=st[9]-neural_wins,rhs_inputs_from_recurrent_neural_proposals=neural_wins,
            next_run_state='generated_device_token_and_committed_graph',recurrent_neural_token_input=True)
    if compound is not None:
        record['execution_roles'].update(root_rhs=neural_wins-child_wins,child_rhs=child_wins,
                                         verification='pending_parent_batch' if compound['batch'] else 'per_wave')
    if replay is not None:
        record['execution_roles'].update(binding_generator='frozen_neural_proposal_replay_with_gpu_verification',
                                         rhs_inputs_from_frozen_proposals=neural_wins,
                                         rhs_inputs_from_recurrent_neural_proposals=0,
                                         recurrent_neural_token_input=False,
                                         next_run_state='frozen_tokens_and_committed_device_graph')
    if host_actor is not None:
        record['execution_roles'].update(binding_generator='cpu_recurrent_neural_proposals_with_gpu_verification',
                                         next_run_state='cpu_generated_latent_and_committed_device_graph')
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
    parser.add_argument('--freshness',type=int,choices=(0,1,2,3,4),default=4,help='0 baseline; 1 table only; 2 table, shard and prefix; 3 omit prefix; 4 omit shard')
    parser.add_argument('--index-repair',action='store_true')
    parser.add_argument('--count-work',action='store_true')
    a=parser.parse_args();execute(a.packet,a.weight,a.port_weights,a.runs,a.rows,a.output,a.capture_prefix,a.reader,a.union,a.directory,a.spine,a.lookup,a.batch_runs,a.tiles,a.token_layout,a.arena,a.router,a.export_only,a.token_cap,a.scalars,a.profile_prims,a.prune_routed,a.row_audit,hot_filter=a.freshness,index_repair=a.index_repair,count_work=a.count_work)
