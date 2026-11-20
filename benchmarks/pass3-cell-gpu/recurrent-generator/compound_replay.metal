// Diagnostic only: replay generated token fields and reconstruct the typed join
// from the decoded parent/child ports. No verdict, match or RHS ordinal is supplied.
kernel void frozen_compound_wave(device int *state,device int *meta,device const float *frozen,
                                 device float *out,device float *trace,constant int &wave,
                                 uint gid [[thread_position_in_grid]]){
    if(gid || state[5] || state[7])return;
    int run=state[3],stride=NEURAL_H+4;
    if(run<1 || run>COM_REPLAY_RUNS){state[5]=29;return;}
    for(int lane=0;lane<2;lane++){
        int slot=(run-1)*4+wave*2+lane;
        device const float *p=frozen+stride*slot;
        for(int i=0;i<stride;i++){out[stride*lane+i]=p[i];trace[stride*slot+i]=p[i];}
        if(!wave)continue;
        device CompoundClaim &claim=claims(meta)[(run-1)*2+lane];
        claim.parent=lane;claim.join=-1;claim.status=0;
        for(int k=0;k<4;k++)meta[NEURAL_BASE+4*(2+lane)+k]=-1;
        if(p[11]==0)continue;
        int parent=int(p[9])-1-(run-1)*2;
        if(parent<0 || parent>=2){state[5]=29;return;}
        int left=int(trace[stride*((run-1)*4+parent)+8])-1,port=int(p[10])-1,right=int(p[8])-1;
        int match=-1;
        for(int j=0;j<COM_JOINS;j++){
            constant int *link=compound_joins+4*j;
            if(link[1]!=left || link[2]!=port || link[3]!=right)continue;
            if(match>=0){state[5]=29;return;}
            match=j;
        }
        if(match<0 || neural_catalog[4*right]<0){state[5]=29;return;}
        claim.parent=parent;claim.join=match;claim.status=1;
    }
}
