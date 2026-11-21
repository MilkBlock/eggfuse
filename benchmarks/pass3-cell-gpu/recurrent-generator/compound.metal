// Slots are append-only during a Pass. Their ids encode issuing Run and child row.
kernel void compound_child(device const int *state, device int *meta, device const float *weights,
                           device const float *parents, device float *child, device float *trace,
                           device const int *receipts, uint lane [[thread_position_in_grid]]){
    if(state[5]||state[7])return;
    int run=state[3],stride=NEURAL_H+4;
    int row_weights=14*COM_JOINS, embedding=row_weights+2*COM_JOINS, null_bias=embedding+8*COM_JOINS;
    float best=weights[null_bias+lane];
    int chosen=-1,origin=int(lane);
    for(int peer=0;peer<2;peer++){
        device const float *p=parents+peer*stride;
        int leaf=int(p[8])-1;
        if(leaf<0)continue;
        int status=COM_BATCH?0:receipts[4*((run-1)*NEURAL_SLOTS+peer)];
        for(int j=0;j<COM_JOINS;j++){
            constant int *link=compound_joins+4*j;
            if(link[1]!=leaf || neural_catalog[4*link[3]]<0)continue;
            device const float *w=weights+14*j;
            float score=w[8]+float(status==1)*w[9]+float(status==2)*w[10]+float(status==3)*w[11]
                +p[10]*w[12]/float(NEURAL_RANKS)+float(peer==int(lane))*w[13]+weights[row_weights+lane*COM_JOINS+j];
            for(int h=0;h<8;h++)score+=p[h]*w[h];
            if(score>best){best=score;chosen=j;origin=peer;}
        }
    }
    device float *out=child+lane*stride;
    for(int h=0;h<8;h++){
        float v=parents[origin*stride+h]+weights[null_bias+2+8*lane+h];
        if(chosen>=0)v+=weights[embedding+8*chosen+h];
        out[h]=tanh(v);
    }
    int right=chosen>=0?compound_joins[4*chosen+3]:-1;
    int port=chosen>=0?compound_joins[4*chosen+2]:-1;
    out[8]=right+1;out[9]=chosen>=0 && !COM_MASK_PARENT?(run-1)*2+origin+1:0;out[10]=port+1;out[11]=float(chosen>=0);
    for(int h=0;h<stride;h++)trace[((run-1)*4+2+lane)*stride+h]=out[h];
    device CompoundClaim &c=claims(meta)[(run-1)*2+lane];
    c.join=chosen;c.parent=COM_MASK_PARENT?-1:origin;c.status=chosen>=0?1:0;
    // Slots 2 and 3 issue continuations, never immediate RHS.
    for(int h=0;h<4;h++)meta[NEURAL_BASE+4*(2+lane)+h]=-1;
}

kernel void compound_resume(device const int *rom,device const long *lits,device int *state,device int *meta,
                            device const long *dyn,device const int *head,device const int *wm,device int *count,
                            device long *tokens,uint lane [[thread_position_in_grid]]){
    if(lane || state[5] || state[7])return;
    int live=state[75],keep=0;
    device int *queue=meta+COM_QUEUE;
    device const int *rs=rom+SETS+2*state[4];
    for(int i=0;i<live;i++){
        int id=queue[i];device CompoundClaim &c=claims(meta)[id];
        int row=c.row,leaf=compound_joins[4*c.join+3];constant int *entry=neural_catalog+4*leaf;
        int rid=entry[0],pivot=entry[1];
        if(meta[6*row+3] || anchor(meta,row)[4]!=c.ticket){
#ifdef COM_FAILURE_RUN
            meta[COM_FAILURE_RUN+id]=state[3];
#endif
            c.status=3;continue;}
        bool scheduled=false;
        for(int k=0;k<rs[0];k++)if(rom[rs[1]+k]==rid){scheduled=true;break;}
        if(!scheduled){queue[keep++]=id;continue;}
        bool duplicate=false;
        for(int n=0;n<2;n++){
            device const int *mark=meta+NEURAL_BASE+4*n;
            duplicate|=mark[0]==rid && mark[1]==pivot && mark[2]==row;
        }
        device int *index=meta+COM_HEAD+2*row;
        if(index[0]==state[3])for(int prev=index[1]-1;prev>=0;prev=claims(meta)[prev].next-1){
            duplicate|=compound_joins[4*claims(meta)[prev].join+3]==leaf;
        }
        if(duplicate){
#ifdef COM_FAILURE_RUN
            meta[COM_FAILURE_RUN+id]=state[3];
#endif
            c.status=4;continue;}
        int before=count[2*rid];
        route<false,true>(state,rom,lits,meta,dyn,head,rom+RULE+7*rid,rom+entry[2],pivot,wm[rid],shard_of(meta,row),
                         PARTS,count+2*rid,tokens+token_offset(rom,rid),nullptr,row);
        c.attempts++;
        if(before==count[2*rid]){queue[keep++]=id;continue;}
        c.next=index[0]==state[3]?index[1]:0;
        index[0]=state[3];index[1]=id+1;c.bank=before;c.verified=state[3];c.status=5;
    }
    state[75]=keep;
}
