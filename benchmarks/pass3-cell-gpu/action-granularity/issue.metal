// Exactly one header per row and source Run. Internal root/unit scoring never publishes a second token.
kernel void issue_unit(device const int *rom,device const long *lits,device const int *state,device int *meta,
                       device const long *dyn,device const int *head,device const int *features,device const float *root_weights,
                       device const float *w,device const float *previous,device float *next,device float *trace,
                       device int *verdict,device int *headers,device long *payload,uint lane [[thread_position_in_grid]]){
    if(state[5]||state[7])return;
    int run=state[3],id=(run-1)*2+lane;
    propose_row(state,features,root_weights,previous,next,trace,verdict,0,lane);
    device float *row=next+12*lane;
    int leaf=int(row[8])-1,anchor_row=int(row[9])-1,rank=int(row[10])-1;
    int jcount=COM_JOINS,unit_bias=8*jcount,unit_row=9*jcount,emb=11*jcount,null_pos=19*jcount;
    int rank_w=null_pos+2,rank_b=rank_w+8*NEURAL_RANKS;
    float best=w[null_pos+lane];int selected=-1;
    for(int j=0;j<jcount;j++){
        constant int *edge=compound_joins+4*j;
        if(edge[1]!=leaf || neural_catalog[4*edge[3]]<0)continue;
        float score=w[unit_bias+j]+w[unit_row+lane*jcount+j];
        for(int h=0;h<8;h++)score+=w[j*8+h]*row[h];
        if(score>best){best=score;selected=j;}
    }
    int code=leaf;
    if(leaf>=0){
        constant int *e=neural_catalog+4*leaf;
        if(ACTION_KIND==2 && selected>=0)code=compound_joins[4*selected];
#if ACTION_KIND==0
        // Proposed tuple and witnesses are sealed before validation. Pick a typed physical address;
        // the pointer head examines no complete key and never calls the exact index.
        code=e[0];device const int *rule=rom+RULE+7*code,*path=rom+e[2];
        device long *out=payload+id*(NINPUT+2);out[0]=e[1];out[1]=-1;
        if(rule[0]==2){
            int table2=path[4];float best_rank=-INFINITY;
            int other=head[table2];
            for(int k=0;k<NEURAL_RANKS && other>=0;k++,other=meta[6*other+5]){
                float score=w[rank_b+(leaf*NEURAL_RANKS+rank)*NEURAL_RANKS+k];
                for(int h=0;h<8;h++)score+=w[rank_w+k*8+h]*row[h];
                if(score>best_rank){best_rank=score;out[1]=other;}
            }
            if(ACTION_CORRUPT)out[1]=-1;
        }
        long env[MAXSLOTS]={};
        for(int pos=0;pos<rule[0];pos++){
            int physical=pos?int(out[1]):anchor_row;if(physical<0)continue;
            device const int *op=path+4*pos,*args=rom+op[2];
            for(int col=0;col<op[1];col++)if(op[3]&(1<<col))env[args[col]]=field(rom,lits,meta,dyn,physical,col);
        }
        for(int k=0;k<rule[4];k++)out[2+k]=env[rom[rule[5]+k]];
#endif
    }
    headers[2*id]=code;headers[2*id+1]=anchor_row;
    for(int h=0;h<8;h++)row[h]=tanh(row[h]+(selected>=0?w[emb+8*selected+h]:0.f));
    for(int h=0;h<12;h++)trace[((run-1)*2+lane)*12+h]=row[h];
}

inline bool validate_tuple(device const int *rom,device const long *lits,device const int *state,device int *meta,
    device const long *dyn,device const int *rule,device const int *path,int pivot,int anchor_row,int wm,
    device const long *payload,device int *cnt,device long *bank){
    device const int *h=anchor(meta,anchor_row);
    if(!h[0]||meta[6*anchor_row+3]||meta[6*anchor_row+4]<wm)return false;
    long env[MAXSLOTS]={};
    for(int pos=0;pos<rule[0];pos++){
        device const int *op=path+4*pos,*args=rom+op[2];int physical=pos?int(payload[1]):anchor_row;
        if(physical<0||physical>=state[0]||meta[6*physical+3]||meta[6*physical]!=op[0])return false;
        for(int j=0;j<op[1];j++){
            long value=field(rom,lits,meta,dyn,physical,j);
            if(op[3]&(1<<j))env[args[j]]=value;
            else if(operand(args[j],env,lits)!=value)return false;
        }
    }
    int width=input_width(rule);
    for(int i=0;i<rule[4];i++)if(env[rom[rule[5]+i]]!=payload[2+i])return false;
    int pos=reserve_token(cnt);if(pos<0)return false;
    device long *out=bank+pos*(width+5);
    for(int i=0;i<rule[4];i++)out[i]=payload[2+i];
    out[width]=anchor_row;out[width+1]=h[0];out[width+2]=h[1];out[width+3]=h[2];
    out[width+4]=long((table(rom,path[0])[1]?0:ROW_CAP)+anchor_row)*DEPTH+pivot;
    return true;
}

kernel void verify_unit(device const int *rom,device const long *lits,device int *state,device int *meta,
    device const long *dyn,device const int *head,device const int *wm,device int *count,device long *tok,
    device const int *headers,device const long *payload,device int *verdict,uint lane [[thread_position_in_grid]]){
    if(lane||state[5]||state[7])return;
    int run=state[3];device const int *rs=rom+SETS+2*state[4];
    for(int i=0;i<4*2;i++)meta[NEURAL_BASE+i]=-1;
    for(int row=0;row<2;row++){
        int id=(run-1)*2+row,code=headers[2*id],seed=headers[2*id+1],leaf=code,selected=-1;
        device int *v=verdict+4*((run-1)*2+row);v[0]=0;v[1]=-1;v[2]=seed;v[3]=-1;
        device CompoundClaim &claim=claims(meta)[id];claim.parent=row;claim.join=-1;
        if(code<0)continue;
#if ACTION_KIND==0
        leaf=-1;
        for(int i=0;i<NEURAL_LEAVES;i++)if(neural_catalog[4*i]==code && neural_catalog[4*i+1]==payload[id*(NINPUT+2)]){leaf=i;break;}
#elif ACTION_KIND==2
        if(code>=NEURAL_LEAVES){
            leaf=-1;
            for(int j=0;j<COM_JOINS;j++)if(compound_joins[4*j]==code){leaf=compound_joins[4*j+1];selected=j;break;}
        }
#endif
        v[0]=2;v[1]=leaf;
        if(leaf<0||leaf>=NEURAL_LEAVES||seed<0||seed>=state[0])continue;
        constant int *e=neural_catalog+4*leaf;int rid=e[0],pivot=e[1];
        if(rid<0||e[3]!=meta[6*seed])continue;
        bool scheduled=false;for(int j=0;j<rs[0];j++)if(rom[rs[1]+j]==rid){scheduled=true;break;}
        if(!scheduled)continue;
        if(selected>=0){claim.join=selected;claim.status=1;}
        device int *first=verdict+4*((run-1)*2);
        if(row && first[0]==1 && first[1]==leaf && first[2]==seed){v[0]=3;continue;}
        device const int *rule=rom+RULE+7*rid;
        int before=count[2*rid];
#if ACTION_KIND==0
        validate_tuple(rom,lits,state,meta,dyn,rule,rom+e[2],pivot,seed,wm[rid],payload+id*(NINPUT+2),count+2*rid,tok+token_offset(rom,rid));
#else
        route<false,true>(state,rom,lits,meta,dyn,head,rule,rom+e[2],pivot,wm[rid],shard_of(meta,seed),PARTS,count+2*rid,
                          tok+token_offset(rom,rid),nullptr,seed);
#endif
        if(count[2*rid]>before){
            v[0]=1;v[3]=before;
            device int *m=meta+NEURAL_BASE+4*row;m[0]=rid;m[1]=pivot;m[2]=seed;m[3]=before;
        }
    }
}
