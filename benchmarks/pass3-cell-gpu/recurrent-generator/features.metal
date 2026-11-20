// Candidate construction uses the scheduled ruleset and typed table address
// space. No LHS predicate, suffix lookup or previous oracle token is read.
inline void read_features(device const int *rom,device const int *state,device int *meta,
                            device const int *head,device const int *wm,device int *features,
                            uint gid) {
    if(state[5]||state[7]){
#if HOST_CONTROL
        if(gid==0)features[1]=-1;
#endif
        return;
    }
    int leaf=int(gid)/NEURAL_RANKS,rank=int(gid)%NEURAL_RANKS;
    constant int *entry=neural_catalog+4*leaf;
    int rid=entry[0],table_id=entry[3],run=state[3];
    device int *f=features+(NEURAL_CAPTURE?(run-1)*NEURAL_ACTIONS*8:0)+gid*8;
    f[0]=-1;f[1]=state[4];
    if(rid<0)return;
    device const int *rs=rom+SETS+2*state[4];
    bool allowed=false;
    for(int i=0;i<rs[0];i++)if(rom[rs[1]+i]==rid){allowed=true;break;}
    if(!allowed)return;
    int row=head[table_id];
    for(int j=0;j<rank && row>=0;j++)row=meta[6*row+5];
    if(row<0)return;
    device const int *m=meta+6*row,*h=anchor(meta,row);
    f[0]=row; f[2]=min(run-m[4],32); f[3]=clamp(m[4]-wm[rid],-32,32);
    f[4]=m[3]; f[5]=min(h[2],16); f[6]=h[0]?min(run-h[3],32):32;
    f[7]=min(table(rom,table_id)[0],16);
#if NEURAL_LABELS
    int reason=m[3]?-3:m[4]<wm[rid]?-4:!h[0]?-5:-6;
    meta[NEURAL_BASE+TRACE_CAP+(run-1)*NEURAL_ACTIONS+gid]=reason;
#endif
}

kernel void neural_features(device const int *rom,device const int *state,device int *meta,
                            device const int *head,device const int *wm,device int *features,
                            uint gid [[thread_position_in_grid]]){
    read_features(rom,state,meta,head,wm,features,gid);
}

#if NEURAL_EDGES
// All searches for this Run observe these exact publications, before any RHS writes.
kernel void neural_snapshot_anchors(device const int *state,device int *meta,uint row [[thread_position_in_grid]]){
    if(!state[5] && !state[7] && row<uint(state[0]))meta[EDGE_BEFORE+row]=anchor(meta,row)[4];
}
#endif
