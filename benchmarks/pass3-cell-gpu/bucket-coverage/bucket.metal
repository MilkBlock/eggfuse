inline int key_bucket(thread long *,int);
inline long directory_key(device const int *,device const long *,device const int *,device const long *,int,int);

inline int projected_hash(device const int *rom,device const long *lits,device const int *meta,
                          device const long *dyn,int row,int mask){
    uint h=0x811c9dc5u;
    for(int k=0;mask;k++,mask>>=1)if(mask&1){
        ulong value=ulong(field(rom,lits,meta,dyn,row,k));
        h=(h^uint(value))*16777619u;h=(h^uint(value>>32))*16777619u;
    }
    return int(h&255);
}
inline bool same_projection(device const int *rom,device const long *lits,device const int *meta,
                            device const long *dyn,int a,int b,int mask){
    for(int k=0;mask;k++,mask>>=1)if((mask&1) && field(rom,lits,meta,dyn,a,k)!=field(rom,lits,meta,dyn,b,k))return false;
    return true;
}
kernel void bucket_verify(device const int *rom,device const long *lits,device int *state,device int *meta,
                          device const long *dyn,device const int *head,device const int *wm,device int *count,
                          device long *tok,device const int *receipts,uint lane [[thread_position_in_grid]]){
    if(lane || state[5] || state[7])return;
    int run=state[3],epoch=state[14];
    meta[BK_ACTIVE]=0;
    device const int *all=receipts+4*(run-1)*NEURAL_SLOTS;
    device const int *rs=rom+SETS+2*state[4];
    for(int slot=0;slot<NEURAL_SLOTS;slot++){
        int input=slot;
        if(BK_CONTROL==3 && slot%2 && all[4*(slot-1)]!=0)input=slot-1;
        device const int *v=all+4*input;
        if(!v[0])continue;
        int leaf=v[1],seed=v[2];
        if(leaf<0 || leaf>=NEURAL_LEAVES || seed<0 || seed>=state[0] || bucket_masks[leaf]<0)continue;
        constant int *entry=neural_catalog+4*leaf;
        int rid=entry[0],pivot=entry[1],t=entry[3],mask=bucket_masks[leaf];
        if(rid<0 || meta[6*seed]!=t)continue;
        bool scheduled=false;
        for(int k=0;k<rs[0];k++)if(rom[rs[1]+k]==rid){scheduled=true;break;}
        if(!scheduled)continue;
        device int *log=meta+BK_LOG+16*((run-1)*NEURAL_SLOTS+slot);
        log[0]=leaf+1;log[1]=seed+1;log[2]=run;log[3]=epoch;
        if(!BUCKET_MODE || (BUCKET_MODE==1 && !BK_UNIQUE)){log[4]=1;continue;}
        device int *versions=meta+BK_VERSION+3*leaf;
        int claimed_run=run,claimed_union=epoch;
        if(BK_CONTROL==2 && versions[2] && versions[2]!=run && versions[1]!=epoch){
            claimed_run=versions[2];claimed_union=versions[1];
        }
        versions[1]=epoch;versions[2]=run;
        if(claimed_run!=run || claimed_union!=epoch){log[4]=4;log[15]=claimed_run;log[7]=claimed_union;continue;}
        if(meta[6*seed+3]){log[4]=6;continue;}
#if BK_UNIQUE
        int arity=table(rom,t)[0]-1;long key[WIDTH];
        for(int k=0;k<arity;k++)key[k]=directory_key(rom,lits,meta,dyn,seed,k);
        int first=head[TABLES+t*256+key_bucket(key,arity)],found=-1;
        for(int row=first;row>=0;row=meta[INDEX_NEXT+row]){
            log[12]++;
            if(meta[6*row+3]==2)continue;
            bool equal=true;
            for(int k=0;k<arity && equal;k++)equal=directory_key(rom,lits,meta,dyn,row,k)==key[k];
            if(equal){found=row;break;}
        }
        if(found!=seed){log[4]=6;continue;}
        if(COUNT_WORK){
            int matches=0;
            for(int row=head[t];row>=0;row=meta[6*row+5]){
                if(meta[6*row+3])continue;
                bool equal=true;
                for(int k=0;k<arity && equal;k++)equal=directory_key(rom,lits,meta,dyn,row,k)==key[k];
                matches+=int(equal);
            }
            if(matches!=1){state[5]=26;return;}
            meta[BK_STATS+1]++;
        }
        log[4]=2;log[5]=1;log[6]=1;log[7]=seed+1;
        device int *mark=meta+BK_MARK+leaf*ROW_CAP+seed;
        log[14]=int(*mark!=run);*mark=run;
#else
#if BUCKET_MODE==2
        device int *heads=meta+BK_HEAD+256*leaf,*links=meta+BK_LINK+leaf*ROW_CAP;
        if(versions[0]!=run){
            for(int b=0;b<256;b++)heads[b]=0;
            for(int row=head[t];row>=0;row=meta[6*row+5]){
                log[9]++;
                if(meta[6*row+3])continue;
                int b=projected_hash(rom,lits,meta,dyn,row,mask);
                links[row]=heads[b];heads[b]=row+1;
            }
            versions[0]=run;
        }
        int first=heads[projected_hash(rom,lits,meta,dyn,seed,mask)]-1,at=-1,extent=0;
        for(int row=first;row>=0;row=links[row]-1){
            log[10]++;
            if(!same_projection(rom,lits,meta,dyn,seed,row,mask))continue;
            if(extent==0)log[7]=row+1;
            if(seed==row)at=extent;
            extent++;
        }
        log[5]=extent;
        if(at<0){log[4]=6;continue;}
        int begin=(at/BK_PAGE)*BK_PAGE,end=min(begin+BK_PAGE,extent),witness[BK_PAGE],n=0,ordinal=0;
        log[15]=begin;
        for(int row=first;row>=0 && ordinal<end;row=links[row]-1){
            log[10]++;
            if(!same_projection(rom,lits,meta,dyn,seed,row,mask))continue;
            if(ordinal++>=begin)witness[n++]=row;
        }
        if(BK_CONTROL==1 && n>1){
            int drop=witness[n-1]==seed?0:n-1;log[7]=witness[drop]+1;
            for(int i=drop;i<n-1;i++)witness[i]=witness[i+1];
            n--;
        }
        // The producer supplies an ordered page witness. The checker owns the
        // directory endpoint and must check every position before closing it.
        if(n!=end-begin){log[4]=5;continue;}
        ordinal=0;bool good=true;
        for(int row=first;row>=0 && ordinal<end;row=links[row]-1){
            log[11]++;
            if(!same_projection(rom,lits,meta,dyn,seed,row,mask))continue;
            if(ordinal>=begin && witness[ordinal-begin]!=row)good=false;
            ordinal++;
        }
        if(!good || ordinal!=end){log[4]=5;continue;}
        if(COUNT_WORK){
            // Independent oracle bypasses the scratch directory and its hash.
            // Directory prepends source table members, reversing their order.
            int reverse=extent;
            for(int row=head[t];row>=0;row=meta[6*row+5]){
                if(meta[6*row+3] || !same_projection(rom,lits,meta,dyn,seed,row,mask))continue;
                int at2=--reverse;
                if(at2>=begin && at2<end && witness[at2-begin]!=row){state[5]=26;return;}
            }
            if(reverse!=0){state[5]=26;return;}
            meta[BK_STATS+1]++;
        }
        log[4]=3;log[6]=n;
        for(int i=0;i<n;i++){
            int row=witness[i];device int *mark=meta+BK_MARK+leaf*ROW_CAP+row;
            if(*mark==run)continue;
            bool checked=false;
            for(int j=0;j<NEURAL_SLOTS;j++)if(all[4*j] && all[4*j+1]==leaf && all[4*j+2]==row)checked=true;
            if(!checked){
                log[13]++;
                int before=count[2*rid];
                route<false,true>(state,rom,lits,meta,dyn,head,rom+RULE+7*rid,rom+entry[2],pivot,wm[rid],
                                 shard_of(meta,row),PARTS,count+2*rid,tok+token_offset(rom,rid),nullptr,row);
                if(count[2*rid]>before){
                    int b=meta[BK_ACTIVE]++;
                    device int *item=meta+BK_BANK+5*((run-1)*NEURAL_SLOTS*BK_PAGE+b);
                    item[0]=rid;item[1]=pivot;item[2]=row;item[3]=before;item[4]=0;
                    log[8]++;
                }
            }
            *mark=run;log[14]++;
        }
#endif
#endif
    }
}
