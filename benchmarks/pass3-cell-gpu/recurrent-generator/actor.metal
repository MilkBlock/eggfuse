// Same weights and equations as model.py. One thread owns each neural row.
// The only discrete inputs from the prior Run are values in the generated
// token. Feature banks are graph observations, never completed exact matches.
constant int W_PREV=NEURAL_H*NEURAL_H;
constant int W_STAGE=W_PREV+3*NEURAL_H;
constant int W_ROW=W_STAGE+32*NEURAL_H;
constant int W_LEAF=W_ROW+NEURAL_ROWS*NEURAL_H;
constant int W_POS=W_LEAF+(NEURAL_LEAVES+1)*NEURAL_H;
constant int W_READ=W_POS+NEURAL_RANKS*NEURAL_H;
constant int W_BIAS=W_READ+6*NEURAL_H;
constant int W_LOCAL=W_BIAS+NEURAL_LEAVES;
constant int W_NULL=W_LOCAL+6;

inline void propose_row(device const int *state,device const int *features,device const float *w,
                           device const float *previous,device float *current,device float *trace,
                           device const int *receipts,int wave,uint row){
    if(state[5]||state[7])return;
    int stride=NEURAL_H+4;
    device const float *prev=previous+stride*row;
#if NEURAL_STOP_NULL
    if(wave && state[74]==state[3]){
        // Advance the ping-pong bank without advancing the recurrent state.
        for(int i=0;i<stride;i++)current[row*stride+i]=prev[i];
        return;
    }
#endif
    device const float *latent=NEURAL_INTERVENTION==2?previous+stride*(NEURAL_ROWS-1-row):prev;
    int tick=(state[3]-1)*NEURAL_WAVES+wave;
    float context[NEURAL_H],chosen_key[NEURAL_H];
#if NEURAL_RECEIPT_HEAD
    // Only the immediately preceding verifier wave is observable. Task identity
    // is (source Run, compiled leaf, stable physical anchor). New Runs reopen it.
    int codes[2]={0,0},leaves[2]={-1,-1},anchors[2]={-1,-1};
    float feedback[8]={};
    if(tick>0 && NEURAL_FEEDBACK>0){
        for(int side=0;side<2;side++){
            int peer=side?1-int(row):int(row);
            device const int *v=receipts+4*((tick-1)*NEURAL_ROWS+peer);
            device const int *ids=receipts+4*((tick-1)*NEURAL_ROWS+(NEURAL_SHUFFLE?1-peer:peer));
            codes[side]=v[0];leaves[side]=ids[1];anchors[side]=ids[2];
            feedback[side]=float(v[0]==1);
            if(NEURAL_FEEDBACK==2){
                feedback[2+side]=float(v[0]==2);
                feedback[4+side]=float(v[0]==2 && v[3]==-4);
                feedback[6+side]=float(v[0]==3);
            }
        }
    }
#endif
    int leaf=int(prev[NEURAL_H]),stage=features[1]%32;
    for(int i=0;i<NEURAL_H;i++){
        float v=w[W_ROW+row*NEURAL_H+i]+w[W_STAGE+stage*NEURAL_H+i]+w[W_LEAF+leaf*NEURAL_H+i];
        if(NEURAL_INTERVENTION!=1) for(int j=0;j<NEURAL_H;j++)v+=w[i*NEURAL_H+j]*latent[j];
        v+=w[W_PREV+3*i]*prev[NEURAL_H+1]/16384.f;
        v+=w[W_PREV+3*i+1]*prev[NEURAL_H+2]/float(NEURAL_RANKS);
        v+=w[W_PREV+3*i+2]*prev[NEURAL_H+3];
#if NEURAL_RECEIPT_HEAD
        for(int j=0;j<8;j++)v+=w[W_NULL+NEURAL_H+1+8*i+j]*feedback[j];
#endif
        context[i]=tanh(v);chosen_key[i]=0;
    }
    float best=w[W_NULL+NEURAL_H];
    for(int j=0;j<NEURAL_H;j++)best+=context[j]*w[W_NULL+j];
    int win=-1;
    for(int action=0;action<NEURAL_ACTIONS && NEURAL_INTERVENTION!=3;action++){
        device const int *f=features+8*action;if(f[0]<0)continue;
        int slot=action/NEURAL_RANKS,rank=action%NEURAL_RANKS;
#if NEURAL_EXCLUDE_CLOSED
        if(wave==1){
            bool closed=false;
            for(int i=0;i<NEURAL_ROWS;i++){
                device const int *v=receipts+4*((tick-1)*NEURAL_ROWS+i);
                closed|=(v[0]==1 || v[0]==3) && v[1]==slot && v[2]==f[0];
            }
            if(closed)continue;
        }
#endif
        float x[6]={f[2]/32.f,f[3]/32.f,f[4]/2.f,f[5]/16.f,f[6]/32.f,f[7]/16.f};
        float keys[NEURAL_H],score=w[W_BIAS+slot];
        for(int k=0;k<6;k++)score+=w[W_LOCAL+k]*x[k];
        for(int j=0;j<NEURAL_H;j++){
            float v=w[W_LEAF+(slot+1)*NEURAL_H+j]+w[W_POS+rank*NEURAL_H+j];
            for(int k=0;k<6;k++)v+=w[W_READ+6*j+k]*x[k];
            keys[j]=tanh(v);score+=context[j]*keys[j];
        }
#if NEURAL_RECEIPT_HEAD
        if(NEURAL_FEEDBACK==2){
            int base=W_NULL+NEURAL_H+1+8*NEURAL_H;
            for(int side=0;side<2;side++){
                if(slot!=leaves[side] || f[0]!=anchors[side])continue;
                int kind=(codes[side]==1 || codes[side]==3)?0:codes[side]==2?1:-1;
                if(kind>=0)score+=w[base+4*int(wave==0)+2*side+kind];
            }
        }
#endif
        if(score>best){
            best=score;win=action;
            for(int j=0;j<NEURAL_H;j++)chosen_key[j]=keys[j];
        }
    }
    device float *out=current+row*stride;
    for(int j=0;j<NEURAL_H;j++)out[j]=tanh(context[j]+chosen_key[j]);
    out[NEURAL_H]=win<0?0:win/NEURAL_RANKS+1;
    out[NEURAL_H+1]=win<0?0:features[win*8]+1;
    out[NEURAL_H+2]=win<0?0:win%NEURAL_RANKS+1;
    out[NEURAL_H+3]=float(win>=0);
    device float *saved=trace+(tick*NEURAL_ROWS+row)*stride;
    for(int j=0;j<stride;j++)saved[j]=out[j];
}

inline void verify_rows(device const int *rom,device const long *lits,device int *state,device int *meta,
                          device const long *dyn,device const int *head,device const int *wm,device int *count,
                          device long *tok,device const float *proposals,device int *verdict,
                          int wave,uint gid){
    if(gid||state[5]||state[7])return;
    device const int *rs=rom+SETS+2*state[4];
    bool emitted=false;
    for(int i=0;i<NEURAL_ROWS;i++){
        int slot=wave*NEURAL_ROWS+i;
        device int *mark=meta+NEURAL_BASE+4*slot;mark[0]=-1;mark[1]=-1;mark[2]=-1;mark[3]=-1;
        device const float *draft=proposals+i*(NEURAL_H+4)+NEURAL_H;
        int leaf=int(draft[0])-1,row=int(draft[1])-1;
        device int *v=verdict+4*((state[3]-1)*NEURAL_SLOTS+slot);
        v[0]=0;v[1]=leaf;v[2]=row;v[3]=-1;
#if NEURAL_STOP_NULL
        if(wave && state[74]==state[3]){v[1]=-1;v[2]=-1;continue;}
#endif
        if(!int(draft[3]))continue;
        emitted=true;
        v[0]=2;
        if(leaf<0||leaf>=NEURAL_LEAVES||row<0||row>=state[0])continue;
        constant int *entry=neural_catalog+4*leaf;
        int rid=entry[0],pivot=entry[1];
        if(rid<0||meta[6*row]!=entry[3])continue;
        bool scheduled=false;
        for(int j=0;j<rs[0];j++)if(rom[rs[1]+j]==rid){scheduled=true;break;}
        if(!scheduled)continue;
        bool duplicate=false;
        for(int j=0;j<slot;j++){
            device const int *prior=verdict+4*((state[3]-1)*NEURAL_SLOTS+j);
            if(prior[0]==1 && prior[1]==leaf && prior[2]==row)duplicate=true;
        }
        if(duplicate){v[0]=3;continue;}
#if NEURAL_RECEIPT_HEAD
        v[3]=meta[6*row+3]?-3:meta[6*row+4]<wm[rid]?-4:!anchor(meta,row)[0]?-5:-6;
#endif
        device const int *rule=rom+RULE+7*rid;
        device int *cnt=count+2*rid;int before=cnt[0];
        route<false,true>(state,rom,lits,meta,dyn,head,rule,rom+entry[2],pivot,wm[rid],shard_of(meta,row),PARTS,
                          cnt,tok+token_offset(rom,rid),nullptr,row);
        if(cnt[0]>before){
            v[0]=1;v[3]=before;
            if(NEURAL_SHADOW){cnt[0]=before;continue;}
            mark[0]=rid;mark[1]=pivot;mark[2]=row;mark[3]=before;
        }
    }
#if NEURAL_STOP_NULL
    if(!emitted)state[74]=state[3];
#endif
}

kernel void neural_propose(device const int *state,device const int *features,device const float *weights,
                           device const float *previous,device float *current,device float *trace,
                           device const int *receipts,constant int &wave,uint row [[thread_position_in_grid]]){
    propose_row(state,features,weights,previous,current,trace,receipts,wave,row);
}

kernel void neural_verify(device const int *rom,device const long *lits,device int *state,device int *meta,
                          device const long *dyn,device const int *head,device const int *wm,device int *count,
                          device long *tokens,device const float *current,device int *receipts,
                          constant int &wave,uint gid [[thread_position_in_grid]]){
    verify_rows(rom,lits,state,meta,dyn,head,wm,count,tokens,current,receipts,wave,gid);
}

#if NEURAL_FUSE
// A single group owns both waves. Only lane zero appends to the RHS bank.
kernel void neural_exchange(device const int *rom,device const long *lits,device int *state,device int *meta,
                            device const long *dyn,device const int *head,device const int *wm,device int *count,
                            device long *tokens,device int *features,device const float *weights,device float *frontier,
                            device float *trace,device int *receipts,uint lane [[thread_index_in_threadgroup]]){
    if(state[5]||state[7])return;
#if NEURAL_FUSE==2
    for(uint i=lane;i<NEURAL_ACTIONS;i+=32)read_features(rom,state,meta,head,wm,features,i);
    threadgroup_barrier(mem_flags::mem_device);
#endif
    constexpr int stride=NEURAL_ROWS*(NEURAL_H+4);
    for(int wave=0;wave<2;wave++){
        device const float *previous=frontier+wave*stride;
        device float *current=frontier+(1-wave)*stride;
        if(lane<NEURAL_ROWS)propose_row(state,features,weights,previous,current,trace,receipts,wave,lane);
        threadgroup_barrier(mem_flags::mem_device);
        if(lane==0)verify_rows(rom,lits,state,meta,dyn,head,wm,count,tokens,current,receipts,wave,0);
        threadgroup_barrier(mem_flags::mem_device);
    }
}
#endif
