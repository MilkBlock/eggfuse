"""Specialize the shared Pass 3 executor at its search/commit boundaries, in this process only."""
import inspect
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
GPU=HERE.parent
sys.path.insert(0,str(GPU))
import run


def replace(source, anchor, new):
    if source.count(anchor)!=1:raise RuntimeError(f'shared executor changed near {anchor}')
    return source.replace(anchor,new)


def patch_shader(source):
    source=replace(source,'// NEURAL_DEVICE_KERNELS',(HERE/'verify.metal').read_text())
    source=replace(source,'    h[0]=root;h[1]=producer;h[2]=depth;h[3]=state[3];h[4]=++state[17];',
                   '''    h[0]=root;h[1]=producer;h[2]=depth;h[3]=state[3];h[4]=++state[17];
    int parent=forest_root_id[producer];
    if(parent>=0 && effect>=0 && meta[FOREST_ROOT+4*parent+2]==state[9]){
        device int *port=meta+FOREST_PORT+3*(forest_port_base[parent]+effect);
        port[0]=state[9];port[1]=row;port[2]=h[4];
#if FOREST_EVENTS
        // The proven source port exists now. Admit only proposals subscribed to this exact effect.
        int key=forest_port_base[parent]+effect;
        for(int j=meta[FOREST_WAITING+key]-1;j>=0;j=meta[FOREST_SUB_LINK+j]-1){
            int claimed=forest_catalog[7*j+2];
            device int *link=meta+FOREST_READY+claimed;
            while(*link && *link-1<j)link=meta+FOREST_READY_LINK+(*link-1);
            meta[FOREST_READY_LINK+j]=*link;*link=j+1;
        }
#endif
    }''')
    source=replace(source,'    int q=rule[0],pivot=-1,last=wm[r],last_fresh=-1;',
                   '''    int q=rule[0],pivot=-1,last=wm[r],last_fresh=-1;
    if(forest_root_id[r]>=0 && meta[FOREST_ROOT+4*forest_root_id[r]]==state[3])return;''')
    source=replace(source,'        device const int *h=anchor(meta,seed);\n#if BLOCK_STUDY',
                   '''        device const int *h=anchor(meta,seed);
        if(!ONE && !CERT){
            device const int *bucket=meta+FOREST_INDEX+2*seed;bool closed=false;
            if(bucket[0]==state[3])for(int j=bucket[1]-1;j>=0;j=meta[FOREST_CLAIMS+8*j+6]-1){
                constant int *c=forest_catalog+7*j;
                closed|=c[2]==int((rule-rom-RULE)/7) && c[3]==pivot;
            }
            if(closed)continue;
        }
#if BLOCK_STUDY''')
    source=replace(source,'            log[0]=run;log[1]=rid;', '''            int root_token=forest_root_id[rid];
            if(root_token>=0){
                device int *a=meta+FOREST_ROOT+4*root_token;
                if(a[0]==run && a[1]==pos)a[2]=state[9];
            }
            if(values[width]>=0){
                device const int *bucket=meta+FOREST_INDEX+2*int(values[width]);
                if(bucket[0]==run)for(int j=bucket[1]-1;j>=0;j=meta[FOREST_CLAIMS+8*j+6]-1){
                    device int *a=meta+FOREST_CLAIMS+8*j;
                    if(forest_catalog[7*j+2]==rid && a[1]==pos)a[2]=state[9];
                }
            }
            log[0]=run;log[1]=rid;''')
    return source


def specialize(p, generate, residual, events=False):
    ids=np.full(p['rules'],-1,dtype=np.int32)
    ids[p['roots']]=np.arange(len(p['roots']))
    starts=np.searchsorted(p['candidates'][:,2],np.arange(p['rules']+1))
    def array(name,x):return 'constant int '+name+'[]={'+','.join(map(str,np.ravel(x)))+'};'
    const='\n'.join([array('forest_catalog',p['candidates']),array('forest_ranges',starts),
        array('forest_root_id',ids),array('forest_port_base',p['publication']),array('forest_projection',p['projections']),
        array('forest_columns',p['columns'])])
    src=inspect.getsource(run.execute)
    src=replace(src,"    lib=torch.mps.compile_shader(constants+'\\n'+shader)", """    forest_root=limits['BLOCK_BASE']
    forest_ports=forest_root+4*len(forest['roots'])
    forest_claims=forest_ports+3*forest['ports']
    forest_index=forest_claims+8*len(forest['candidates'])
    waiting=forest_index+2*limits['ROW_CAP']
    sub_link=waiting+forest['ports']
    ready=sub_link+len(forest['candidates'])
    ready_link=ready+forest['rules']
    end=ready_link+len(forest['candidates']) if event_mode else waiting
    forest_defines=f'#define FOREST_ROOT {forest_root}\\n#define FOREST_PORT {forest_ports}\\n#define FOREST_CLAIMS {forest_claims}\\n#define FOREST_INDEX {forest_index}\\n#define FOREST_EVENTS {int(event_mode)}\\n#define FOREST_VISITS {end}\\n#define FOREST_WAITING {waiting}\\n#define FOREST_SUB_LINK {sub_link}\\n#define FOREST_READY {ready}\\n#define FOREST_READY_LINK {ready_link}\\n'
    lib=torch.mps.compile_shader(constants+'\\n'+forest_defines+forest_constants+'\\n'+patch_shader(shader))""")
    src=replace(src,'    meta=zeros(((meta_words+5)//6,6))','    meta=zeros(((end+6)//6,6))')
    src=replace(src,'    def infer():','''    def infer():
        root_ids,claims,root_latent=generate()
        if event_mode:lib.subscribe_forest(meta,claims,threads=1)
        # The host enqueues every neural token before scheduling even the first source Run.
''')
    src=replace(src,"                if neural is None or neural.get('complete_residual',True) or bootstrap:",'''                lib.verify_forest(prog,literal,state,meta,dyn,head,wm,count,tokens,root_ids,claims,threads=1)
                if residual_completion:''')
    src=replace(src,'    def take(t,stop):return t[:stop].cpu().numpy()', '''    mem=meta.view(-1)
    root_log=mem[forest_root:forest_ports].reshape(-1,4).cpu().numpy()
    child_log=mem[forest_claims:forest_index].reshape(-1,8).cpu().numpy()
    np.savez_compressed(root/'forest.npz',roots=root_log,children=child_log,visits=mem[end].cpu().numpy(),
                        outputs=mem[forest_ports:forest_claims].reshape(-1,3).cpu().numpy())
    def take(t,stop):return t[:stop].cpu().numpy()''')
    src=replace(src,"    (root/'run.json').write_text", """    origins=int((root_log[:,2]>0).sum())+int((child_log[:,2]>0).sum())
    if not residual_completion and origins!=st[9]:raise ValueError('unattributed no-residual RHS')
    record['execution_roles'].update(binding_generator='precomputed_forest_and_source_residual' if residual_completion else 'precomputed_forest_only',
            rhs_inputs_from_exact_search=st[9]-origins,rhs_inputs_from_static_empty_lhs=int((root_log[:,2]>0).sum()),
            rhs_inputs_from_neural_port_claims=int((child_log[:,2]>0).sum()),generated_before_first_run=True)
    (root/'run.json').write_text""")
    namespace=dict(run.__dict__,forest=p,generate=generate,patch_shader=patch_shader,forest_constants=const,residual_completion=residual,event_mode=events)
    exec(compile(src,str(HERE/'adapter.py')+'::execute','exec'),namespace)
    return namespace['execute']
