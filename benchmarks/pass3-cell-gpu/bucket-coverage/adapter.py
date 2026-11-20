"""Install figure 45 kernels in a private copy of the real Pass 3 entry point."""
import inspect
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
GPU=HERE.parent
sys.path.insert(0,str(GPU))
import run


def replace(source,where,new):
    if source.count(where)!=1:raise ValueError(f'executor boundary mismatch: {where}')
    return source.replace(where,new)


def plans(image,entries,panel):
    packet=json.loads((image/'ingress.json').read_bytes())
    layout=json.loads((image/'device.json').read_bytes())['layout']
    masks=[];lookup=[-1]*(layout['RULES']*layout['DEPTH'])
    for leaf,(rule,pivot,_,table) in enumerate(entries):
        if rule<0:masks.append(-1);continue
        lookup[rule*layout['DEPTH']+pivot]=leaf
        query=packet['rules'][rule]['q'];relation,cols=query[pivot]
        assert relation==table and len(cols)==len(packet['tables'][table]['schema'])
        arity=len(cols)-1
        if arity==0:masks.append(-1);continue
        full=(1<<arity)-1
        if panel=='unique':masks.append(full);continue
        shared={s for i,(other,args) in enumerate(query) if i!=pivot and isinstance(other,int) for s in args}
        cols_mask=sum(1<<i for i,s in enumerate(cols) if s in shared or s<0)
        # Select a proper input-key projection. Prefer the query's shared
        # columns. With a free scan, slice the pivot by its leading input;
        # unary full keys use the result projection for the inverse relation.
        if not cols_mask or (cols_mask & full)==full:
            cols_mask=1 if arity>1 else 1<<arity
        assert cols_mask & full != full
        masks.append(cols_mask)
    return masks,lookup


def specialize(image,entries,panel,mode,control='intact',page=4,clock=None):
    masks,lookup=plans(image,entries,panel)
    head='\n'.join(['constant int bucket_masks[]={'+','.join(map(str,masks))+'};',
                    'constant int bucket_leaf[]={'+','.join(map(str,lookup))+'};'])
    controls={'intact':0,'omit':1,'stale':2,'duplicate':3}
    cfg=dict(mode={'positive':0,'unique':1,'range':2}[mode],unique=panel=='unique',control=controls[control],
             page=page)
    def patch(shader):
        code=(HERE/'bucket.metal').read_text()
        where='inline int insert_row(device const int *rom,'
        shader=replace(shader,where,code+'\n'+where)
        where='        if(!ONE && NEURAL_CLOSE){'
        shader=replace(shader,where,'''        if(!ONE && BUCKET_MODE && (BK_UNIQUE || BUCKET_MODE==2)){
            int leaf=bucket_leaf[int((rule-rom-RULE)/7)*DEPTH+pivot];
            if(leaf>=0 && meta[BK_MARK+leaf*ROW_CAP+seed]==state[3]){
                if(COUNT_WORK)atomic_fetch_add_explicit((device atomic_int *)(const_cast<device int *>(meta)+BK_STATS+0),1,memory_order_relaxed);
                continue;
            }
        }
'''+where)
        where='#if NEURAL_CAPTURE\n            meta[NEURAL_BASE+state[9]-1]'
        shader=replace(shader,where,'''#if BUCKET_MODE==2
            for(int b=0;b<meta[BK_ACTIVE];b++){
                device int *item=meta+BK_BANK+5*((run-1)*NEURAL_SLOTS*BK_PAGE+b);
                if(item[0]==rid && item[3]==pos){item[4]=state[9];break;}
            }
#endif
'''+where)
        return shader
    src=inspect.getsource(run.execute)
    where="    lib=torch.mps.compile_shader(constants+'\\n'+shader)"
    src=replace(src,where,'''    bkbase=nbase+(4+steps)*per_run
    bkmark=bkbase
    bkstats=bkmark+(cap_count*leaves if bucket_cfg['mode'] else 0)
    bkactive=bkstats+16
    bklogs=bkactive+1
    bkbanks=bklogs+steps*per_run*16
    bkvers=bkbanks+(steps*per_run*bucket_cfg['page']*5 if bucket_cfg['mode']==2 else 0)
    bkheads=bkvers+3*leaves
    bklinks=bkheads+(leaves*256 if bucket_cfg['mode']==2 and not bucket_cfg['unique'] else 0)
    bkend=bklinks+(leaves*cap_count if bucket_cfg['mode']==2 and not bucket_cfg['unique'] else 0)
    defs=dict(BK_MARK=bkmark,BK_STATS=bkstats,BK_ACTIVE=bkactive,BK_LOG=bklogs,BK_BANK=bkbanks,
              BK_VERSION=bkvers,BK_HEAD=bkheads,BK_LINK=bklinks,BK_PAGE=bucket_cfg['page'],
              BUCKET_MODE=bucket_cfg['mode'],BK_CONTROL=bucket_cfg['control'],BK_UNIQUE=int(bucket_cfg['unique']))
    constants+='\\n'+'\\n'.join(f'#define {k} {v}' for k,v in defs.items())+'\\n'+bucket_head
    lib=torch.mps.compile_shader(constants+'\\n'+patch_bucket(shader))'''.replace('cap_count',"limits['ROW_CAP']"))
    where='    meta=zeros(((meta_words+5)//6,6))'
    src=replace(src,where,'    meta_words=bkend\n'+where)
    where="                if neural is None or neural.get('complete_residual',True) or bootstrap:"
    src=replace(src,where,'''                lib.bucket_verify(prog,literal,state,meta,dyn,head,wm,count,tokens,verdict,threads=1)
'''+where)
    where='    def take(t,stop):return t[:stop].cpu().numpy()'
    src=replace(src,where,'''    mem=meta.view(-1)
    bklog=mem[bklogs:bklogs+st[11]*per_run*16].reshape(-1,per_run,16).cpu().numpy()
    bkbank=mem[bkbanks:bkbanks+st[11]*per_run*bucket_cfg['page']*5].reshape(-1,per_run*bucket_cfg['page'],5).cpu().numpy() if bucket_cfg['mode']==2 else np.empty((st[11],0,5),dtype=np.int32)
    bkstats_out=mem[bkstats:bkstats+16].cpu().numpy()
    np.savez_compressed(root/'buckets.npz',log=bklog,bank=bkbank,stats=bkstats_out,
                        meta_bytes=np.asarray((bkend-bkbase)*4))
'''+where)
    where="    (root/'run.json').write_text"
    src=replace(src,where,'''    sibling_wins=int((bkbank[:,:,4]!=0).sum())
    record['execution_roles']['rhs_inputs_from_bucket_enumeration']=sibling_wins
    record['execution_roles']['rhs_inputs_from_exact_search']-=sibling_wins
'''+where)
    if clock is not None:
        call='''                            lib.neural_verify(prog,literal,state,meta,dyn,head,wm,count,tokens,current,verdict,wave,
                                              threads=1,arg_casts={11:'int32'})'''
        src=replace(src,call,"                            key=(iteration,wave)\n                            if key in phase_clock:phase_clock[key][0].record()\n"+call+"\n                            if key in phase_clock:phase_clock[key][1].record()")
        call="                lib.bucket_verify(prog,literal,state,meta,dyn,head,wm,count,tokens,verdict,threads=1)"
        src=replace(src,call,"                key=(iteration,2)\n                if key in phase_clock:phase_clock[key][0].record()\n"+call+"\n                if key in phase_clock:phase_clock[key][1].record()")
    if clock is None and (mode=='positive' or (mode=='unique' and panel=='partial')):
        call='                lib.bucket_verify(prog,literal,state,meta,dyn,head,wm,count,tokens,verdict,threads=1)'
        src=replace(src,call,'                if count_work:\n    '+call)
    values=dict(run.__dict__,bucket_cfg=cfg,bucket_head=head,patch_bucket=patch,phase_clock=clock)
    exec(compile(src,str(HERE/'adapter.py')+'::execute','exec'),values)
    return values['execute']
