"""Instrument the original certified route and the actual min commit, scoped to the recognized family."""
from pathlib import Path
import inspect,sys
import numpy as np

HERE=Path(__file__).resolve().parent;GPU=HERE.parent
sys.path.insert(0,str(GPU))
import run


def replace(source,old,new):
    if source.count(old)!=1:raise ValueError(f'upstream source mismatch: {old}')
    return source.replace(old,new)


def shader(source):
    source=replace(source,'inline void touch_row(device int *state,device int *meta,device int *head,int row,int t,int epoch){',
                   'inline void touch_row(device int *state,device int *meta,device int *head,int row,int t,int epoch){\n    reinterpret_cast<device long *>(meta+NUM_RECEIPTS)[row]=0;')
    # Structural selector runs after typed/delta candidate preparation and before the first suffix read.
    source=replace(source,'        long env[MAXSLOTS];int witness[DEPTH];bool matched=true;', '''        int numeric_id=int((rule-rom-RULE)/7),index=num_index[numeric_id],record=-1;
        if(index>=0 && !ONE && !CERT){
            device int *log=const_cast<device int *>(meta)+NUM_BASE;
            record=atomic_fetch_add_explicit((device atomic_int *)log,1,memory_order_relaxed);
            if(record>=TRACE_CAP){state[5]=5;return;}
            device int *f=log+1+record*16;
            f[0]=state[3];f[1]=numeric_id;f[2]=seed;f[3]=pivot;
            f[4]=min(state[3]-meta[6*seed+4],32);f[5]=clamp(meta[6*seed+4]-last,-32,32);
            f[6]=min(h[2],16);f[7]=min(state[3]-h[3],32);f[8]=int(rule[0]);
            f[9]=int(numeric_id%31);f[10]=h[1]%31;
            float score=num_selector[7];for(int j=0;j<7;j++)score+=float(f[4+j])/32.f*num_selector[j];
            f[11]=int(score>=num_threshold[index]);
        }
        if(NUM_ONLY && index>=0 && (record<0 || !meta[NUM_BASE+1+record*16+11]))continue;
        long env[MAXSLOTS];int witness[DEPTH];bool matched=true;''')
    source=replace(source,'                    row=find_key(rom,lits,meta,dyn,head,t,n-1,key);','''                    row=-1;
                    bool eligible=record>=0 && n==2 && num_receipt_tables[t] && key[0]>=0 && key[0]<NUM_KEY_CAP;
                    if(eligible){
                        device int *stats=const_cast<device int *>(meta)+NUM_STATS;
                        atomic_fetch_add_explicit((device atomic_int *)stats,1,memory_order_relaxed);
                        if(NUM_DIRECT){
                            int receipt=meta[NUM_KEYS+(num_receipt_tables[t]-1)*NUM_KEY_CAP+key[0]];
                            if(receipt){
                                device const long *proof=reinterpret_cast<device const long *>(meta+NUM_OUTCOMES)+16*(receipt-1);
                                int physical=int(proof[9]);
                                if(proof[10]==t && proof[13]==key[0] && !meta[6*physical+3] &&
                                   reinterpret_cast<device const long *>(meta+NUM_RECEIPTS)[physical]==receipt &&
                                   proof[11]==meta[6*physical+4]){
                                    if(NUM_DIRECT==2 && proof[4]!=proof[5]){
                                        atomic_fetch_add_explicit((device atomic_int *)(stats+2),1,memory_order_relaxed);
                                    }else{
                                        row=physical;
                                        atomic_fetch_add_explicit((device atomic_int *)(stats+1),1,memory_order_relaxed);
                                    }
                                }
                            }
                        }
                    }
                    if(row<0)row=find_key(rom,lits,meta,dyn,head,t,n-1,key);
                    if(record>=0 && row>=0 && num_receipt_tables[t] && !meta[6*row+3]){
                        int prior=int(reinterpret_cast<device const long *>(meta+NUM_RECEIPTS)[row]);
                        if(prior){
                            device const long *port=reinterpret_cast<device const long *>(meta+NUM_OUTCOMES)+16*(prior-1);
                            if(port[9]==row && port[11]==meta[6*row+4]){
                                device int *f=const_cast<device int *>(meta)+NUM_BASE+1+record*16;
                                if(!f[14])f[14]=prior;else if(!f[15]&&f[14]!=prior)f[15]=prior;
                            }
                        }
                    }''')
    source=replace(source,'    if(PART==2)return;\n    bool routed[DEPTH];','    if(PART==2 || (NUM_ONLY && num_index[r]>=0))return;\n    bool routed[DEPTH];')
    source=replace(source,'                if(CERT)witness[pos]=row;','''                if(record>=0 && num_receipt_tables[t]){
                    int prior=int(reinterpret_cast<device const long *>(meta+NUM_RECEIPTS)[row]);
                    device int *ports=const_cast<device int *>(meta)+NUM_PARENTS+8*record;
                    for(int arg=0;arg<num_slots[5*index];arg++){
                        if(num_slots[5*index+arg+1]!=args[n-1])continue;
                        ports[2*arg]=row+1;ports[2*arg+1]=prior;
                    }
                }
                if(CERT)witness[pos]=row;''')
    # Choose a visible receipt port to read only if its version and relation still agree.
    first='                    long v=field(rom,lits,meta,dyn,row,j);\n                    if(op[3]'
    source=replace(source,first,'''                    long v;bool supplied=false;
                    if(NUM_DIRECT && record>=0 && j==n-1 && num_receipt_tables[t]){
                        int prior=int(reinterpret_cast<device const long *>(meta+NUM_RECEIPTS)[row]);
                        if(prior){
                            device const long *port=reinterpret_cast<device const long *>(meta+NUM_OUTCOMES)+16*(prior-1);
                            if(port[9]==row && port[11]==meta[6*row+4]){
                                if(NUM_DIRECT==2 && port[4]!=port[5]){
                                    atomic_fetch_add_explicit((device atomic_int *)(const_cast<device int *>(meta)+NUM_STATS+3),1,memory_order_relaxed);
                                }else{v=port[5];supplied=true;}
                            }
                        }
                    }
                    if(!supplied)v=field(rom,lits,meta,dyn,row,j);
                    if(op[3]''')
    source=replace(source,'        if(!matched)continue;\n#if NEURAL_LABELS','''        if(!matched)continue;
        if(record>=0){
            device int *f=const_cast<device int *>(meta)+NUM_BASE+1+16*record;
            f[12]=1;
            device long *args=reinterpret_cast<device long *>(const_cast<device int *>(meta)+NUM_ARGS)+6*record;
            for(int j=0;j<num_slots[5*index];j++)args[j]=env[num_slots[5*index+j+1]];
            if(NUM_MODE==1 || NUM_MODE==2){
                float guess=num_regressor[5*index+4];
                for(int j=0;j<num_slots[5*index];j++)guess+=num_regressor[5*index+j]*float(args[j]);
                args[4]=(isfinite(guess)&&fabs(guess)<9.22e18f)?long(rint(guess)):LONG_MIN;
                if(NUM_MODE==2)args[4]=LONG_MIN;
                // Execute the compiler's original add/copy/literal order, rejecting signed overflow.
                long stack[16];int depth=0;bool defined=true;
                for(int pc=num_ranges[index];pc<num_ranges[index+1];pc++){
                    long op=num_code[2*pc],arg=num_code[2*pc+1];
                    if(op==0){stack[depth++]=env[int(arg)];}
                    else if(op==1){stack[depth++]=arg;}
                    else{
                        long b=stack[--depth],a=stack[depth-1],v=long(ulong(a)+ulong(b));stack[depth-1]=v;
                        if(((a^v)&(b^v))<0){defined=false;break;}
                    }
                }
                args[5]=int(defined && depth==1 && stack[0]==args[4]);
                if(NUM_ONLY && !args[5])continue;
            }
        }
#if NEURAL_LABELS''')
    source=replace(source,'        if(CERT){\n            device int *dst=certs+j*(DEPTH+3);','''        if(record>=0)const_cast<device int *>(meta)[NUM_BANK+numeric_id*2*TOKEN_CAP+j]=record+1;
        if(CERT){
            device int *dst=certs+j*(DEPTH+3);''')
    source=replace(source,'            log[0]=run;log[1]=rid;', '''            int provenance=-1;
            if(num_index[rid]>=0 && values[width+1]){
                int id=meta[NUM_BANK+rid*2*TOKEN_CAP+pos]-1;
                if(id>=0){
                    device int *f=meta+NUM_BASE+1+16*id;
                    if(f[0]==run && f[1]==rid && f[2]==values[width] && f[3]==values[width+4]%DEPTH){provenance=id;f[13]=state[9];}
                }
            }
            log[0]=run;log[1]=rid;''')
    source=replace(source,'                bool had_old=found>=0;long previous=0;', '''                long proposed=args[arity];
                device long *outcome=nullptr;
                if(num_index[rid]>=0){
                    outcome=reinterpret_cast<device long *>(meta+NUM_OUTCOMES)+16*(state[9]-1);
                    outcome[0]=run;outcome[1]=rid;outcome[2]=found>=0;
                    outcome[3]=found>=0?field(rom,lits,meta,dyn,found,arity):0;
                    outcome[4]=proposed;outcome[5]=(found>=0 && outcome[3]<proposed)?outcome[3]:proposed;
                    outcome[6]=!(found>=0 && outcome[5]==outcome[3]);outcome[7]=provenance+1;outcome[10]=t;outcome[13]=args[0];
                    if(num_receipt_tables[t] && arity==1 && args[0]>=0 && args[0]<NUM_KEY_CAP){
                        meta[NUM_KEYS+(num_receipt_tables[t]-1)*NUM_KEY_CAP+args[0]]=state[9];
                    }
                    if(provenance>=0 && meta[NUM_BASE+1+16*provenance+11]){
                        device const long *prediction=reinterpret_cast<device const long *>(meta+NUM_ARGS)+6*provenance;
                        outcome[12]=prediction[4];
                        if(NUM_MODE==1 || NUM_MODE==2){
                            if(prediction[4]==proposed){args[arity]=prediction[4];outcome[8]=1;}
                            else outcome[8]=2; // use the exact source result after rejecting the numeric proposal
                        }else outcome[8]=1;
                    }
                }
                bool had_old=found>=0;long previous=0;''')
    source=replace(source,'                    if(old==v){publish_anchor(','''                    if(old==v){
                        if(outcome){outcome[5]=old;outcome[9]=found;outcome[11]=meta[6*found+4];
                            reinterpret_cast<device long *>(meta+NUM_RECEIPTS)[found]=state[9];}
                        publish_anchor(''')
    source=replace(source,'                publish_anchor(rom,state,meta,t,found,cursor,rid,depth,pending,k);\n                log_write',
                   '''                if(outcome){outcome[5]=field(rom,lits,meta,dyn,found,arity);outcome[9]=found;outcome[11]=meta[6*found+4];
                    reinterpret_cast<device long *>(meta+NUM_RECEIPTS)[found]=state[9];}
                publish_anchor(rom,state,meta,t,found,cursor,rid,depth,pending,k);
                log_write''')
    return source


def specialize(plans,ingress,model=None,mode='structural',direct=True,domain_only=False):
    slots=[];bytecode=[];program_ranges=[0];ids=np.full(len(ingress['rules']),-1,np.int32)
    for i,p in enumerate(plans):
        ids[p['rule']]=i
        slots.extend([len(p['slots']),*p['slots'],*([0]*(4-len(p['slots'])))])
        for op,operand in p['code']:bytecode.append((['slot','literal','add'].index(op),operand))
        program_ranges.append(len(bytecode))
    def array(typ,name,x):
        def literal(v):return f'{float(v):.9e}f' if typ=='float' else str(int(v))
        return f'constant {typ} {name}[]={{'+','.join(map(literal,np.ravel(x)))+'};'
    reg=([model['numeric'].get(str(p['rule']),model.get('shape_numeric',{}).get(f"{len(p['slots'])}/{p['literal']}",[0.]*5)) for p in plans] if model else np.zeros((len(plans),5)))
    names=sorted({p['table'] for p in plans})
    static='\n'.join([array('long','num_code',bytecode),array('int','num_ranges',program_ranges),array('int','num_index',ids),array('int','num_slots',slots),array('int','num_receipt_tables',[names.index(t['name'])+1 if t['name'] in names and len(t['schema'])==2 and t['schema'][0]['kind']=='eq' else 0 for t in ingress['tables']]),
                      array('float','num_threshold',[model.get('thresholds',{}).get(str(p['rule']),0.) if model else 0. for p in plans]),array('float','num_selector',model['selector'] if model else [0.]*8),array('float','num_regressor',reg)])
    src=inspect.getsource(run.execute)
    anchor="    lib=torch.mps.compile_shader(constants+'\\n'+shader)"
    src=replace(src,anchor,'''    numeric_base=limits['BLOCK_BASE']
    nt=limits['TRACE_CAP'];nc=limits['ROW_CAP'];num_args=numeric_base+2+16*nt
    if num_args%2:num_args+=1
    num_outcomes=num_args+12*nt;num_receipts=num_outcomes+32*nt;num_bank=num_receipts+2*nc
    num_keys=num_bank+layout['RULES']*2*token_cap;num_key_cap=nc+layout['NSYMBOLS']+2
    num_stats=num_keys+num_tables*num_key_cap;num_parents=num_stats+4;num_end=num_parents+8*nt
    defs='\\n'.join(f'#define {k} {v}' for k,v in dict(NUM_BASE=numeric_base,NUM_ARGS=num_args,NUM_OUTCOMES=num_outcomes,
        NUM_PARENTS=num_parents,NUM_KEYS=num_keys,NUM_KEY_CAP=num_key_cap,NUM_STATS=num_stats,NUM_BANK=num_bank,NUM_RECEIPTS=num_receipts,NUM_MODE=numeric_mode,NUM_DIRECT=int(numeric_direct),NUM_ONLY=int(numeric_only)).items())
    lib=torch.mps.compile_shader(constants+'\\n'+defs+'\\n'+numeric_constants+'\\n'+numeric_shader(shader))''')
    src=replace(src,'meta=zeros(((meta_words+5)//6,6))','meta=zeros(((num_end+5)//6,6))')
    src=replace(src,'    def take(t,stop):return t[:stop].cpu().numpy()', '''    mem=meta.view(-1);records=int(mem[numeric_base].item());assert records<=nt
    np.savez_compressed(root/'numeric.npz',input_ports=mem[num_parents:num_parents+8*records].reshape(-1,4,2).cpu().numpy(),
        port_stats=mem[num_stats:num_stats+4].cpu().numpy(),features=mem[numeric_base+1:numeric_base+1+records*16].reshape(-1,16).cpu().numpy(),
        args=mem[num_args:num_args+12*records].view(torch.int64).reshape(-1,6).cpu().numpy(),
        outcomes=mem[num_outcomes:num_outcomes+32*st[9]].view(torch.int64).reshape(-1,16).cpu().numpy())
    def take(t,stop):return t[:stop].cpu().numpy()''')
    src=replace(src,"    (root/'run.json').write_text", """    record['numeric_roles']=dict(candidate_provider='typed published Spine entrances from the source engine',
        structural_selector='trained logistic anchor selector',matcher='GPU certified route and ordinary residual',
        number_source='checked learned candidate' if numeric_mode else 'source i64 program',
        merge='source min on the committed value',ordinary_numeric_residual=not numeric_only)
    (root/'run.json').write_text""")
    env=dict(run.__dict__,numeric_shader=shader,numeric_constants=static,numeric_mode=['structural','predict','wrong'].index(mode),numeric_direct=direct,numeric_only=domain_only,num_tables=len(names))
    exec(compile(src,str(HERE/'adapter.py')+'::execute','exec'),env)
    return env['execute']
