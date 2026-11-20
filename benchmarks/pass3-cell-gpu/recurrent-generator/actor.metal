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

kernel void neural_propose(device const int *state,device const int *features,device const float *w,
                           device const float *previous,device float *current,device float *trace,
                           uint row [[thread_position_in_grid]]){
    if(state[5]||state[7])return;
    int stride=NEURAL_H+4;
    device const float *prev=previous+stride*row;
    device const float *latent=NEURAL_INTERVENTION==2?previous+stride*(NEURAL_ROWS-1-row):prev;
    float context[NEURAL_H],chosen_key[NEURAL_H];
    int leaf=int(prev[NEURAL_H]),stage=features[1]%32;
    for(int i=0;i<NEURAL_H;i++){
        float v=w[W_ROW+row*NEURAL_H+i]+w[W_STAGE+stage*NEURAL_H+i]+w[W_LEAF+leaf*NEURAL_H+i];
        if(NEURAL_INTERVENTION!=1) for(int j=0;j<NEURAL_H;j++)v+=w[i*NEURAL_H+j]*latent[j];
        v+=w[W_PREV+3*i]*prev[NEURAL_H+1]/16384.f;
        v+=w[W_PREV+3*i+1]*prev[NEURAL_H+2]/float(NEURAL_RANKS);
        v+=w[W_PREV+3*i+2]*prev[NEURAL_H+3];
        context[i]=tanh(v);chosen_key[i]=0;
    }
    float best=w[W_NULL+NEURAL_H];
    for(int j=0;j<NEURAL_H;j++)best+=context[j]*w[W_NULL+j];
    int win=-1;
    for(int action=0;action<NEURAL_ACTIONS && NEURAL_INTERVENTION!=3;action++){
        device const int *f=features+8*action;if(f[0]<0)continue;
        int slot=action/NEURAL_RANKS,rank=action%NEURAL_RANKS;
        float x[6]={f[2]/32.f,f[3]/32.f,f[4]/2.f,f[5]/16.f,f[6]/32.f,f[7]/16.f};
        float keys[NEURAL_H],score=w[W_BIAS+slot];
        for(int k=0;k<6;k++)score+=w[W_LOCAL+k]*x[k];
        for(int j=0;j<NEURAL_H;j++){
            float v=w[W_LEAF+(slot+1)*NEURAL_H+j]+w[W_POS+rank*NEURAL_H+j];
            for(int k=0;k<6;k++)v+=w[W_READ+6*j+k]*x[k];
            keys[j]=tanh(v);score+=context[j]*keys[j];
        }
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
    device float *saved=trace+((state[3]-1)*NEURAL_ROWS+row)*stride;
    for(int j=0;j<stride;j++)saved[j]=out[j];
}

kernel void neural_verify(device const int *rom,device const long *lits,device int *state,device int *meta,
                          device const long *dyn,device const int *head,device const int *wm,device int *count,
                          device long *tok,device const float *proposals,device int *verdict,
                          uint gid [[thread_position_in_grid]]){
    if(gid||state[5]||state[7])return;
    device const int *rs=rom+SETS+2*state[4];
    for(int i=0;i<NEURAL_ROWS;i++){
        device int *mark=meta+NEURAL_BASE+4*i;mark[0]=-1;mark[1]=-1;mark[2]=-1;mark[3]=-1;
        device const float *draft=proposals+i*(NEURAL_H+4)+NEURAL_H;
        int leaf=int(draft[0])-1,row=int(draft[1])-1;
        device int *v=verdict+4*((state[3]-1)*NEURAL_ROWS+i);
        v[0]=0;v[1]=leaf;v[2]=row;v[3]=-1;
        if(!int(draft[3]))continue;
        v[0]=2;
        if(leaf<0||leaf>=NEURAL_LEAVES||row<0||row>=state[0])continue;
        constant int *entry=neural_catalog+4*leaf;
        int rid=entry[0],pivot=entry[1];
        if(rid<0||meta[6*row]!=entry[3])continue;
        bool scheduled=false;
        for(int j=0;j<rs[0];j++)if(rom[rs[1]+j]==rid){scheduled=true;break;}
        if(!scheduled)continue;
        bool duplicate=false;
        for(int j=0;j<i;j++){
            device const int *prior=verdict+4*((state[3]-1)*NEURAL_ROWS+j);
            if(prior[0]==1 && prior[1]==leaf && prior[2]==row)duplicate=true;
        }
        if(duplicate){v[0]=3;continue;}
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
}
