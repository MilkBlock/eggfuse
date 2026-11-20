#if FOREST_EVENTS
kernel void subscribe_forest(device int *meta,device const int *proposal,uint lane [[thread_position_in_grid]]){
    if(lane)return;
    for(int idx=forest_ranges[RULES]-1;idx>=0;idx--){
        device const int *token=proposal+6*idx;
        if(!token[0])continue;
        if(token[5]<0){meta[FOREST_CLAIMS+8*idx+7]=1;continue;}
        int key=forest_catalog[7*idx+6];
        meta[FOREST_SUB_LINK+idx]=meta[FOREST_WAITING+key];meta[FOREST_WAITING+key]=idx+1;
    }
}
#endif
// All root and child claims already exist in one immutable device buffer before this kernel runs.
// Each child may win at most one RHS; published graph rows carry the actual run-local generation.
kernel void verify_forest(device const int *rom,device const long *lits,device int *state,device int *meta,
                          device const long *dyn,device const int *head,device const int *wm,device int *count,
                          device long *tokens,device const int *root_ids,device const int *proposal,uint lane [[thread_position_in_grid]]){
    if(lane || state[5] || state[7])return;
    int run=state[3];
    device const int *rs=rom+SETS+2*state[4];
    for(int k=0;k<rs[0];k++){
        int rid=rom[rs[1]+k];device const int *rule=rom+RULE+7*rid;
        int root=forest_root_id[rid],width=input_width(rule);
        if(root>=0 && root_ids[root]==rid && !rule[0] && !rule[4] && (!rule[6]||wm[rid]<0)){
            device int *audit=meta+FOREST_ROOT+4*root;
            if(!audit[2]){
                int pos=reserve_token(count+2*rid);
                if(pos<0)return;
                device long *out=tokens+token_offset(rom,rid)+pos*(width+5);
                out[width]=-1;out[width+1]=0;out[width+2]=0;out[width+3]=0;out[width+4]=0;
                audit[0]=run;audit[1]=pos;
            }
        }
#if FOREST_EVENTS
        // Drop resolved or displaced parent generations as this consumer becomes scheduled.
        device int *slot=meta+FOREST_READY+rid;
        while(*slot){
            int idx=*slot-1;
#if COUNT_WORK
            meta[FOREST_VISITS]++;
#endif
            device const int *prior=meta+FOREST_CLAIMS+8*idx;
            device const int *published=meta+FOREST_PORT+3*forest_catalog[7*idx+6];
            if(prior[2] || !published[0] || anchor(meta,published[1])[4]!=published[2] || meta[6*published[1]+3]){
                *slot=meta[FOREST_READY_LINK+idx];continue;
            }
            slot=meta+FOREST_READY_LINK+idx;
#else
        for(int idx=forest_ranges[rid];idx<forest_ranges[rid+1];idx++){
#if COUNT_WORK
            meta[FOREST_VISITS]++;
#endif
#endif
            device const int *token=proposal+6*idx;
            if(!token[0])continue;
            // Only a compiled continuation from this exact published parent effect can discharge this claim.
            constant int *c=forest_catalog+7*idx;device int *audit=meta+FOREST_CLAIMS+8*idx;
            if(token[5]<0){audit[7]=1;continue;}
            if(audit[2])continue;
            device const int *port=meta+FOREST_PORT+3*c[6];
            if(!port[0])continue;
            int row=port[1],ticket=port[2];
            if(row<0 || meta[6*row]!=c[5] || anchor(meta,row)[4]!=ticket || meta[6*row+3])continue;
            audit[5]++;
            int before=count[2*rid];
            if(token[5]){
                // Universal one-atom proof was checked in the global post-generation sweep. Publish
                // its projection only when this exact parent generation is visible and delta-owned.
                int proj=forest_projection[rid];device const int *h=anchor(meta,row);
                if(proj<0){audit[7]=1;continue;}
                if(!h[0] || meta[6*row+4]<wm[rid])continue;
                int pos=reserve_token(count+2*rid);
                if(pos<0)return;
                device long *out=tokens+token_offset(rom,rid)+pos*(width+5);
                for(int j=0;j<rule[4];j++)out[j]=field(rom,lits,meta,dyn,row,forest_columns[proj+j]);
                out[width]=row;out[width+1]=h[0];out[width+2]=h[1];out[width+3]=h[2];
                out[width+4]=long((table(rom,c[5])[1]?0:ROW_CAP)+row)*DEPTH+c[3];
            }else{
                route<false,true>(state,rom,lits,meta,dyn,head,rule,rom+c[4],c[3],wm[rid],shard_of(meta,row),PARTS,
                                  count+2*rid,tokens+token_offset(rom,rid),nullptr,row);
            }
            if(count[2*rid]==before)continue;
            audit[0]=run;audit[1]=before;audit[3]=row;audit[4]=ticket;
            device int *bucket=meta+FOREST_INDEX+2*row;
            audit[6]=bucket[0]==run?bucket[1]:0;bucket[0]=run;bucket[1]=idx+1;
        }
    }
}
