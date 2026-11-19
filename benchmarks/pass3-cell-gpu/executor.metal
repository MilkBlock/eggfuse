#include <metal_stdlib>
using namespace metal;
// Initial members stay template-backed. Dynamic rows store only newly committed values.
// meta = table, Cell instance (-1 for a dynamic row), member op, subsumed, epoch, next.
// state = row count, pc, changed Run count, Run ordinal, current set, fault, stop rid,
// finished, changed in current Run, RHS log count, effect log count, last complete Run.
inline device const int *table(device const int *rom,int t){return rom+TABLE+4*t;}
inline long rawfield(device const int *rom,device const long *lits,device const int *meta,
                  device const long *dyn,int row,int col){
    device const int *m=meta+6*row;
    if(m[1]<0)return dyn[row*WIDTH+col];
    device const int *inst=rom+INSTANCE+3*m[1];
    device const int *tp=rom+TEMPLATE+2*inst[0];
    device const int *op=rom+tp[1]+3*m[2];
    int parameter=rom[op[2]+col];
    if(parameter<0){
        device const int *from=rom+tp[1]+3*(-1-parameter);
        parameter=rom[from[2]+from[1]-1];
    }
    return lits[rom[inst[1]+parameter]];
}
// Mutable class representatives and their invalidation epoch are separate
// from the stable physical member addresses used to decode initial rows.
constant int UF_SIZE=NSYMBOLS+ROW_CAP+2;
constant int UNION_LOG=6*ROW_CAP+2*UF_SIZE+2*TRACE_CAP;
constant int BIRTH_RUN=UNION_LOG+4*UF_SIZE;
inline int root_id(device const int *meta,int v){
    device const int *parent=meta+6*ROW_CAP;
    while(parent[v])v=parent[v];
    return v;
}
inline bool unite(device int *state,device int *meta,long a,long b){
    if(a<=0 || b<=0 || a>=UF_SIZE || b>=UF_SIZE){state[5]=14;return false;}
    int x=root_id(meta,int(a)),y=root_id(meta,int(b));
    if(x==y)return false;
    int hi=max(x,y),lo=min(x,y);
    int log=state[14]++;
    if(log>=UF_SIZE){state[5]=17;return false;}
    device int *u=meta+UNION_LOG+4*log;
    u[0]=state[3];u[1]=state[0];u[2]=hi;u[3]=lo;
    meta[6*ROW_CAP+hi]=lo;
    meta[6*ROW_CAP+UF_SIZE+hi]=state[3];state[8]=1;state[12]=1;
    return true;
}
// The source queues explicit RHS unions until all matches of this Run commit.
inline void submit_union(device int *state,device int *meta,long a,long b){
#if FENCE_UNIONS
    int n=state[13];if(n>=TRACE_CAP){state[5]=16;return;}
    device int *queue=meta+6*ROW_CAP+2*UF_SIZE;
    queue[2*n]=int(a);queue[2*n+1]=int(b);state[13]++;
#else
    unite(state,meta,a,b);
#endif
}
inline long field(device const int *rom,device const long *lits,device const int *meta,
                  device const long *dyn,int row,int col){
    long v=rawfield(rom,lits,meta,dyn,row,col);
    return (table(rom,meta[6*row])[3]&(1<<col))?long(root_id(meta,int(v))):v;
}
constant int SHARD_NEXT=BIRTH_RUN+8*ROW_CAP;
constant int SHARD_HEAD=TABLES*(1+256*USE_INDEX);
constant int ROW_OWNER=SHARD_NEXT+ROW_CAP;
inline int shard_of(device const int *meta,int row){return LEARN_OWNER?meta[ROW_OWNER+row]:row%PARTS;}
inline void append_shard(device const int *rom,device int *meta,device int *head,int id,int t,long first){
    if(TILES>1 || LEARN_OWNER){
        int shard=id%PARTS;
        if(LEARN_OWNER){
            ulong v=ulong(first);
            uint h=uint(v)^uint(v>>32);h^=h>>16;h*=0x45d9f3bu;h^=h>>16;
            uint code=(h&63u) | ((t&1)<<6) | (uint(table(rom,t)[0]>2)<<7);
            int row=rom[ROUTER+code];
            shard=row+2*((id/2)%TILES);meta[ROW_OWNER+id]=shard;
        }
        int bucket=SHARD_HEAD+t*PARTS+shard;
        meta[SHARD_NEXT+id]=head[bucket];head[bucket]=id;
    }
}
kernel void inject(device const int *rom,device const int *slots,device int *state,device int *meta,
                   device int *head,device int *order,device const long *lits,device const long *dyn,uint gid [[thread_position_in_grid]]){
    if(gid)return;
    for(int t=0;t<TABLES;t++)head[t]=-1;
    if(TILES>1 || LEARN_OWNER)for(int j=0;j<TABLES*PARTS;j++)head[SHARD_HEAD+j]=-1;
    for(int i=0;i<NINST;i++){
        if(slots[i]<0 || slots[i]>=NINST || order[slots[i]]){state[5]=1;return;}
        // Neural addresses select physical instances. Their verified stable
        // identity, rather than bank order, determines the execution layout.
        int cell=slots[i];order[cell]=1;
        device const int *inst=rom+INSTANCE+3*cell,*tp=rom+TEMPLATE+2*inst[0];
        for(int j=0;j<tp[0];j++){
            int t=rom[tp[1]+3*j],id=state[0]++;
            if(id>=ROW_CAP){state[5]=2;return;}
            device int *m=meta+6*id;
            m[0]=t;m[1]=cell;m[2]=j;m[3]=(inst[2]>>j)&1;m[4]=0;m[5]=head[t];head[t]=id;append_shard(rom,meta,head,id,t,(LEARN_OWNER && table(rom,t)[0]>1)?rawfield(rom,lits,meta,dyn,id,0):0);
        }
    }
}
inline long operand(int i,thread long *env,device const long *lits){return i>=0?env[i]:lits[-1-i];}
inline bool exact_prim(int op,long a,long b,thread long &out){
    switch(op){
        case 0:case 15:out=0;return a!=b;
        case 1:if(!b || (a==LONG_MIN && b==-1))return false;out=a%b;return true;
        case 2:{
            ulong x=a<0?0UL-ulong(a):ulong(a), y=b<0?0UL-ulong(b):ulong(b);
            ulong limit=((a<0)!=(b<0))?(1UL<<63):ulong(LONG_MAX);
            if(x && y>limit/x)return false;
            out=long(ulong(a)*ulong(b));return true;
        }
        case 3:out=long(ulong(a)+ulong(b));return ((a^out)&(b^out))>=0;
        case 4:out=long(ulong(a)-ulong(b));return ((a^b)&(a^out))>=0;
        case 5:if(!b || (a==LONG_MIN && b==-1))return false;out=a/b;return true;
        case 6:out=0;return a<b;
        case 7:out=0;return a<=b;
        case 8:out=0;return a>b;
        case 9:out=0;return a>=b;
        case 10:out=a&&b;return true;
        case 11:out=a<b;return true;
        case 12:out=a>b?a:b;return true;
        case 13:out=a<b?a:b;return true;
        case 14:out=a||b;return true;
    }
    return false;
}
inline bool prim(device int *state,int op,long a,long b,thread long &out){
    bool fp=false;
    if(SCALAR_MODE && op!=1 && op!=5 && op!=10 && op!=14 && op!=15){
        // Never cast equivalence-class IDs to floating point. Bound operands
        // before multiplying; a guarded integer result must fit in 24 bits.
        long lim=SCALAR_MODE==1?16777216L:268435456L;
        fp=a>=-lim && a<=lim && b>=-lim && b<=lim;
        if(fp && SCALAR_MODE==1){
            long result=op==2?a*b:(op==3?a+b:(op==4?a-b:0));
            fp=result>=-lim && result<=lim;
        }
    }
    if(PROFILE_PRIMS){
        device atomic_int *c=(device atomic_int *)(state+19);
        atomic_fetch_add_explicit(c+op,1,memory_order_relaxed);
        if(fp)atomic_fetch_add_explicit(c+16+op,1,memory_order_relaxed);
    }
    if(!fp)return exact_prim(op,a,b,out);
    float x=float(a),y=float(b);
    switch(op){
        case 0:out=0;return x!=y;
        case 2:out=long(x*y);return true;
        case 3:out=long(x+y);return true;
        case 4:out=long(x-y);return true;
        case 6:out=0;return x<y;
        case 7:out=0;return x<=y;
        case 8:out=0;return x>y;
        case 9:out=0;return x>=y;
        case 11:out=x<y;return true;
        case 12:out=long(max(x,y));return true;
        case 13:out=long(min(x,y));return true;
    }
    return false;
}
kernel void primitive_probe(device const long *inputs,device long *answers,device int *stats,
                            uint gid [[thread_position_in_grid]]){
    device const long *in=inputs+gid*3;long value=0;
    bool ok=prim(stats,int(in[0]),in[1],in[2],value);
    answers[2*gid]=int(ok);answers[2*gid+1]=ok?value:0;
}
inline void do_next_run(device const int *rom,device int *state,device int *regs,device int *counts,uint gid){
    if(gid||state[5]||state[7])return;
    while(state[1]<NCTRL){
        device const int *i=rom+CONTROL+4*state[1]++;
        if(i[0]==0){state[4]=i[1];state[3]++;state[8]=0;
            return;}
        if(i[0]==1)regs[i[1]]=state[2];
        if(i[0]==2 && regs[i[1]]!=state[2])state[1]=i[2];
        if(i[0]==3)regs[i[1]]=i[2];
        if(i[0]==4 && --regs[i[1]] && regs[i[2]]!=state[2])state[1]=i[3];
    }
    state[7]=1;
}
inline int find_key(device const int *,device const long *,device const int *,device const long *,
                    device const int *,int,int,thread long *);
inline device const int *anchor(device const int *meta,int row){return meta+BIRTH_RUN+ROW_CAP+5*row;}
inline device int *anchor(device int *meta,int row){return meta+BIRTH_RUN+ROW_CAP+5*row;}
inline void publish_anchor(device const int *rom,device int *state,device int *meta,int t,int row,
                           int root,int producer,int depth){
    if(!SPINE_ON || row<0 || !root || !rom[DEMANDED+t])return;
    device int *h=anchor(meta,row);
    h[0]=root;h[1]=producer;h[2]=depth;h[3]=state[3];h[4]=++state[17];
}
inline int input_width(device const int *rule){return PACK_TOKENS?rule[4]:NINPUT;}
inline int token_offset(device const int *rom,int rid){
    return (PACK_TOKENS?rom[TOKEN_BASE+rid]:rid*TOKEN_WIDTH)*(SHARED_ARENA?2:PARTS)*TOKEN_CAP;
}
inline void token_error(device int *count,int code){
    if(SHARED_ARENA)atomic_store_explicit((device atomic_int *)(count+1),code,memory_order_relaxed);
    else *count=code;
}
inline int reserve_token(device int *count){
    int pos=SHARED_ARENA?atomic_fetch_add_explicit((device atomic_int *)count,1,memory_order_relaxed):(*count)++;
    if(pos<0 || pos>=(SHARED_ARENA?2:1)*TOKEN_CAP){token_error(count,-2);return -1;}
    return pos;
}
inline void route(device int *state,device const int *rom,device const long *lits,device const int *meta,
                  device const long *dyn,device const int *head,device const int *rule,
                  device const int *path,int pivot,int last,int lane,int lanes,
                  device int *cnt,device long *bank){
    int table0=path[0];
    for(int seed=(TILES>1 || LEARN_OWNER)?head[SHARD_HEAD+table0*PARTS+lane]:head[table0];seed>=0;seed=(TILES>1 || LEARN_OWNER)?meta[SHARD_NEXT+seed]:meta[6*seed+5]){
        device const int *h=anchor(meta,seed);
        if(shard_of(meta,seed)!=lane || meta[6*seed+3] || !h[0] || meta[6*seed+4]<last)continue;
        long env[MAXSLOTS];bool matched=true;
        for(int pos=0;pos<rule[0] && matched;pos++){
            device const int *op=path+4*pos,*args=rom+op[2];int t=op[0],n=op[1],row=seed;
            if(t<0){
                long v=0;matched=prim(state,-1-t,operand(args[0],env,lits),operand(args[1],env,lits),v);
                if(op[3]&(1<<(n-1)))env[args[n-1]]=v;
                else matched &= operand(args[n-1],env,lits)==v;
            }else{
                if(pos){
                    long key[WIDTH];for(int j=0;j<n-1;j++)key[j]=operand(args[j],env,lits);
                    row=find_key(rom,lits,meta,dyn,head,t,n-1,key);
                    if(row<0 || meta[6*row+3]){matched=false;break;}
                }
                for(int j=0;j<n;j++){
                    long v=field(rom,lits,meta,dyn,row,j);
                    if(op[3]&(1<<j))env[args[j]]=v;
                    else if(operand(args[j],env,lits)!=v){matched=false;break;}
                }
            }
        }
        if(!matched)continue;
        int j=reserve_token(cnt);if(j<0)return;
        int width=input_width(rule);device long *out=bank+j*(width+5);
        for(int k=0;k<rule[4];k++)out[k]=env[rom[rule[5]+k]];
        out[width]=seed;out[width+1]=h[0];out[width+2]=h[1];out[width+3]=h[2];
        out[width+4]=long((table(rom,table0)[1]?0:ROW_CAP)+seed)*DEPTH+pivot;
    }
}
inline void do_search(device const int *rom,device const long *lits,device int *state,
                   device const int *meta,device const long *dyn,device const int *head,
                   device const int *wm,device int *count,device long *tok,constant int &lanes,
                   uint gid){
    if(state[5]||state[7])return;
    device const int *rs=rom+SETS+2*state[4];int idx=gid/PARTS,lane=gid%PARTS;
    if(idx>=rs[0])return;
    int r=rom[rs[1]+idx];device const int *rule=rom+RULE+7*r;
    int bank=SHARED_ARENA?2*r:r*PARTS+lane;if(!SHARED_ARENA)count[bank]=0;
    int width=input_width(rule);device long *target=tok+token_offset(rom,r)+(SHARED_ARENA?0:lane)*TOKEN_CAP*(width+5);
    int q=rule[0],pivot=-1,last=wm[r];
    for(int j=0;j<q;j++){int t=rom[rule[1]+4*j];if(t>=0){if(pivot<0)pivot=j;if(head[t]<0)return;}}
    if(pivot<0 && lane)return;
    if(q==0 && rule[6] && last>=0)return;
    device const int *sp=rom+SPINE+4*r;
    if(SPINE_ON)for(int k=0;k<sp[0];k++){
        device const int *e=rom+sp[1]+2*k;
        route(state,rom,lits,meta,dyn,head,rule,rom+e[1],e[0],last,lane,PARTS,count+bank,target);
        if(!SHARED_ARENA && count[bank]<0)return;
    }
    bool routed[DEPTH];routed[0]=false;
    long env[MAXSLOTS];int cur[DEPTH],epoch[DEPTH],witness[DEPTH];cur[0]=-2;epoch[0]=0;
    int depth=0,visits=0;
    while(depth>=0){
        if(++visits>SEARCH_CAP){token_error(count+bank,-1);return;}
        if(depth==q){
            if(!routed[depth] && (!rule[6] || epoch[depth]>=last)){
                int pos=reserve_token(count+bank);if(pos<0)return;
                device long *out=target+pos*(width+5);
                for(int j=0;j<rule[4];j++)out[j]=env[rom[rule[5]+j]];
                out[width]=pivot>=0?witness[pivot]:-1;out[width+1]=0;out[width+3]=0;out[width+4]=0;
            }
            depth--;continue;
        }
        device const int *op=rom+rule[1]+4*depth,*args=rom+op[2];int t=op[0];
        bool point=USE_POINTS && t>=0 && !(op[3]&((1<<(op[1]-1))-1));
        if(cur[depth]==-2){
            if(point){
                long key[WIDTH];for(int j=0;j<op[1]-1;j++)key[j]=operand(args[j],env,lits);
                cur[depth]=find_key(rom,lits,meta,dyn,head,t,op[1]-1,key);
            }else cur[depth]=t<0?0:(((TILES>1 || LEARN_OWNER) && depth==pivot)?head[SHARD_HEAD+t*PARTS+lane]:head[t]);
        }
        int row=cur[depth];
        if(row<0){cur[depth]=-2;depth--;continue;}
        bool ok=true;int version=epoch[depth];
        if(t<0){
            cur[depth]=-1;long val=0;
            ok=prim(state,-1-t,operand(args[0],env,lits),operand(args[1],env,lits),val);
            int lastcol=op[1]-1,key=args[lastcol];
            if(op[3]&(1<<lastcol))env[key]=val;
            else ok &= operand(key,env,lits)==val;
        }else{
            device const int *m=meta+6*row;cur[depth]=point?-1:(((TILES>1 || LEARN_OWNER) && depth==pivot)?meta[SHARD_NEXT+row]:m[5]);
            if(m[3] || (depth==pivot && shard_of(meta,row)!=lane))continue;
            // A certified functional continuation owns every suffix from this
            // specific published witness. Other pivots remain in the residual join.
            if(PRUNE_ROUTED && SPINE_ON && (sp[2]&(1<<depth)) && m[4]>=last && anchor(meta,row)[0])continue;
            for(int j=0;j<op[1];j++){
                long v=field(rom,lits,meta,dyn,row,j);int key=args[j];
                if(op[3]&(1<<j))env[key]=v;
                else if(operand(key,env,lits)!=v){ok=false;break;}
            }
            version=max(version,m[4]);witness[depth]=row;
        }
        if(ok){routed[depth+1]=routed[depth] || (SPINE_ON && t>=0 && (sp[2]&(1<<depth)) && meta[6*row+4]>=last && anchor(meta,row)[0]);
            depth++;epoch[depth]=version;cur[depth]=-2;}
    }
}
constant int INDEX_NEXT=BIRTH_RUN+6*ROW_CAP;
constant int INDEX_BUCKET=INDEX_NEXT+ROW_CAP;
inline int key_bucket(thread long *key,int arity){
    uint h=2166136261u;
    for(int k=0;k<arity;k++){
        ulong v=ulong(key[k]);
        h=(h^uint(v))*16777619u;h=(h^uint(v>>32))*16777619u;
    }
    return int((h^(h>>16)) & 255u);
}
inline void link_key(device int *meta,device int *head,int row,int t,int bucket){
    int index=TABLES+t*256+bucket;
    meta[INDEX_NEXT+row]=head[index];head[index]=row;meta[INDEX_BUCKET+row]=bucket;
}
inline void unlink_key(device int *meta,device int *head,int row,int t){
    int index=TABLES+t*256+meta[INDEX_BUCKET+row];
    device int *slot=head+index;
    while(*slot>=0 && *slot!=row)slot=meta+INDEX_NEXT+*slot;
    if(*slot==row)*slot=meta[INDEX_NEXT+row];
}
kernel void seed_index(device const int *rom,device int *meta,device const long *dyn,device int *head,
                       uint t [[thread_position_in_grid]]){
    if(t>=TABLES)return;
    for(int j=0;j<256;j++)head[TABLES+t*256+j]=-1;
    int arity=table(rom,t)[0]-1;
    for(int row=head[t];row>=0;row=meta[6*row+5]){
        long key[WIDTH];for(int j=0;j<arity;j++)key[j]=dyn[(ROW_CAP+row)*WIDTH+j];
        link_key(meta,head,row,t,key_bucket(key,arity));
    }
}
kernel void seed_keys(device const int *rom,device const long *lits,device const int *state,
                      device const int *meta,device long *dyn,uint row [[thread_position_in_grid]]){
    if(row>=uint(state[0]))return;
    int n=table(rom,meta[6*row])[0]-1;
    for(int j=0;j<n;j++)dyn[(ROW_CAP+row)*WIDTH+j]=rawfield(rom,lits,meta,dyn,row,j);
}
inline long directory_key(device const int *rom,device const long *lits,device const int *meta,
                          device const long *dyn,int row,int col){
#if PUBLISHED_KEYS
    return dyn[(ROW_CAP+row)*WIDTH+col];
#else
    return field(rom,lits,meta,dyn,row,col);
#endif
}
inline int find_key(device const int *rom,device const long *lits,device const int *meta,
                    device const long *dyn,device const int *head,int table_id,int arity,thread long *values){
    int start=USE_INDEX?head[TABLES+table_id*256+key_bucket(values,arity)]:head[table_id];
    for(int row=start;row>=0;row=USE_INDEX?meta[INDEX_NEXT+row]:meta[6*row+5]){
        if(meta[6*row+3]==2)continue;
        bool same=true;
        for(int j=0;j<arity;j++)if(directory_key(rom,lits,meta,dyn,row,j)!=values[j]){same=false;break;}
        if(same)return row;
    }
    return -1;
}
inline int insert_row(device const int *rom,device int *state,device int *meta,device long *dyn,device int *head,
                      int t,int n,thread long *values){
    int id=state[0];if(id>=ROW_CAP){state[5]=2;return -1;}
    state[0]++;device int *m=meta+6*id;m[0]=t;m[1]=-1;m[2]=0;m[3]=0;m[4]=state[3];m[5]=head[t];head[t]=id;append_shard(rom,meta,head,id,t,n>1?values[0]:0);
    meta[BIRTH_RUN+id]=state[18]?-state[3]:state[3];
    for(int j=0;j<n;j++){
        dyn[id*WIDTH+j]=values[j];
#if PUBLISHED_KEYS
        if(j<n-1)dyn[(ROW_CAP+id)*WIDTH+j]=values[j];
#endif
    }
    if(USE_INDEX)link_key(meta,head,id,t,key_bucket(values,n-1));
    state[8]=1;return id;
}
inline int compare(device const long *a,device const long *b,int n){
    for(int j=0;j<n;j++){if(a[j]<b[j])return -1;if(a[j]>b[j])return 1;}return 0;
}
inline long merge_value(device const int *rom,device const long *lits,device int *state,device int *meta,
                        device long *dyn,device int *head,int t,long old,long v){
    int kind=table(rom,t)[2];
    if(old==v || kind==1)return old;
    if(kind==2)return v;
    if(kind==3)return old<v?old:v;
    if(kind==4)return old>v?old:v;
    if(kind==5){long small=old<v?old:v;return small>1?small:1;}
    if(kind>=16){
        int ctor=kind-16;long pair[3]={old,v,0};
        int row=find_key(rom,lits,meta,dyn,head,ctor,2,pair);
        if(row<0){pair[2]=NSYMBOLS+1+state[0];row=insert_row(rom,state,meta,dyn,head,ctor,3,pair);}
        return row<0?0:field(rom,lits,meta,dyn,row,2);
    }
    state[5]=12;return old;
}
inline void log_write(device int *state,device long *writes,int rid,int ordinal,int t,int row,
                      thread long *key,int arity,bool had_old,long old,long value){
    if(state[10]>=TRACE_CAP){state[5]=5;return;}
    device long *w=writes+(state[10]++)*(WIDTH+7);
    w[0]=state[3];w[1]=rid;w[2]=t;w[3]=row;
    for(int j=0;j<arity;j++)w[4+j]=key[j];w[4+arity]=value;
    w[WIDTH+4]=int(had_old);w[WIDTH+5]=old;w[WIDTH+6]=ordinal;
}
inline void repair(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head,device long *writes){
#if FENCE_UNIONS
    device const int *queue=meta+6*ROW_CAP+2*UF_SIZE;
    for(int j=0;j<state[13];j++)unite(state,meta,queue[2*j],queue[2*j+1]);
    state[13]=0;
#endif
    int passes=0;
    while(state[12] && !state[5]){
        if(++passes>ROW_CAP){state[5]=15;return;}
        state[12]=0;
        for(int row=0;row<state[0];row++){
            device int *m=meta+6*row;if(m[3]==2)continue;
            int t=m[0];device const int *spec=table(rom,t);int last=spec[0]-1;
            bool changed=false,key_changed=false;
            for(int j=0;j<=last;j++)if(spec[3]&(1<<j)){
                int v=int(rawfield(rom,lits,meta,dyn,row,j));
                while(meta[6*ROW_CAP+v]){
                    if(meta[6*ROW_CAP+UF_SIZE+v]==state[3]){changed=true;key_changed|=j<last;}
                    v=meta[6*ROW_CAP+v];
                }
            }
            if(!changed)continue;
            m[4]=state[3];if(!key_changed)continue;
            long key[WIDTH];
            for(int j=0;j<last;j++)key[j]=field(rom,lits,meta,dyn,row,j);
            for(int other=head[t];other>=0;other=meta[6*other+5]){
                if(other==row || meta[6*other+3]==2)continue;
                bool same=true;for(int j=0;j<last;j++)if(key[j]!=directory_key(rom,lits,meta,dyn,other,j)){same=false;break;}
                if(!same)continue;
                int keep=PUBLISHED_KEYS?other:min(row,other),drop=PUBLISHED_KEYS?row:max(row,other);
                long old=field(rom,lits,meta,dyn,keep,last),v=field(rom,lits,meta,dyn,drop,last);
                if(spec[1])unite(state,meta,old,v);
                else{
                    long next=merge_value(rom,lits,state,meta,dyn,head,t,old,v);
                    if(next!=old){if(meta[6*keep+1]>=0){state[5]=13;return;}log_write(state,writes,-1,-1,t,keep,key,last,true,old,next);dyn[keep*WIDTH+last]=next;meta[6*keep+4]=state[3];}
                }
                if(meta[6*drop+3]==1){meta[6*keep+3]=1;meta[6*keep+4]=state[3];}
                if(SPINE_ON){
                    device int *lost=anchor(meta,drop),*saved=anchor(meta,keep);
                    if(lost[3]==state[3] && lost[4]>saved[4])for(int j=0;j<5;j++)saved[j]=lost[j];
                }
                if(USE_INDEX)unlink_key(meta,head,drop,t);
                meta[6*drop+3]=2;if(drop==row)break;
            }
#if PUBLISHED_KEYS
            if(meta[6*row+3]!=2){
                if(USE_INDEX && key_bucket(key,last)!=meta[INDEX_BUCKET+row]){
                    unlink_key(meta,head,row,t);link_key(meta,head,row,t,key_bucket(key,last));
                }
                for(int j=0;j<last;j++)dyn[(ROW_CAP+row)*WIDTH+j]=key[j];
            }
#endif
        }
    }
}
inline void do_commit(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head,device int *wm,device const int *count,device long *tok,
                   device long *rhs,device long *writes,device int *runs,device int *resumes,constant int &lanes,
                   uint gid){
    if(gid||state[5]||state[7])return;
    int run=state[3],base_rhs=state[9],base_write=state[10];device const int *rs=rom+SETS+2*state[4];
    for(int idx=0;idx<rs[0];idx++){
        int rid=rom[rs[1]+idx];device const int *rule=rom+RULE+7*rid;
        wm[rid]=run;int ordered[512],n=0;
        int width=input_width(rule),stride=width+5;device const long *bank=tok+token_offset(rom,rid);
        for(int lane=0;lane<(SHARED_ARENA?1:PARTS);lane++){
            int bound=SHARED_ARENA?count[2*rid]:count[PARTS*rid+lane];
            if(SHARED_ARENA && count[2*rid+1])bound=count[2*rid+1];if(bound<0){state[5]=bound==-1?3:4;state[6]=rid;return;}
            for(int i=0;i<bound;i++){
                if(n>=512){state[5]=4;state[6]=rid;return;}
                int pos=lane*TOKEN_CAP+i,at=n;
                while(at>0){
                    device const long *a=bank+ordered[at-1]*stride,*b=bank+pos*stride;
                    int order=compare(a,b,rule[4]);
                    bool priority=a[width+3]<b[width+3] || (a[width+3]==b[width+3] && a[width+4]>b[width+4]);
                    if(order<0 || (order==0 && !priority))break;
                    ordered[at]=ordered[at-1];at--;
                }
                ordered[at]=pos;n++;
            }
        }
        for(int i=0;i<n;i++){
            device const long *values=bank+ordered[i]*stride;
            if(i && compare(values,bank+ordered[i-1]*stride,rule[4])==0)continue;
#if AUDIT_ROWS
            int proposals[2]={0,0};
            for(int j=i;j<n;j++){
                device const long *candidate=bank+ordered[j]*stride;
                if(compare(values,candidate,rule[4])!=0)break;
                int row=candidate[width]<0?0:shard_of(meta,int(candidate[width]))%lanes;
                proposals[row]++;
            }
            device int *evidence=runs+6*RUN_CAP+6*(run-1);
            evidence[0]+=proposals[0];evidence[1]+=proposals[1];
            if(proposals[0] && proposals[1])evidence[4]++;
            else evidence[2+int(proposals[1]!=0)]++;
            if(proposals[0]>1)evidence[5]+=proposals[0]-1;
            if(proposals[1]>1)evidence[5]+=proposals[1]-1;
#endif
            if(state[9]>=TRACE_CAP){state[5]=5;return;}
            long env[MAXSLOTS],args[WIDTH+2];
            device long *log=rhs+(state[9]++)*(NINPUT+4);
            log[0]=run;log[1]=rid;log[2]=values[width]<0?0:shard_of(meta,int(values[width]))%lanes;log[3]=values[width];
            for(int j=0;j<rule[4];j++){env[rom[rule[5]+j]]=values[j];log[4+j]=values[j];}
            int cursor=0,depth=0;
            if(SPINE_ON){
                cursor=int(values[width+1]);
                if(cursor){
                    depth=int(values[width+3]);
                    if(state[16]>=TRACE_CAP){state[5]=18;return;}
                    device int *ev=resumes+6*state[16]++;
                    ev[0]=run;ev[1]=state[9]-base_rhs;ev[2]=cursor-1;
                    ev[3]=int(values[width+2]);ev[4]=rid;ev[5]=depth;depth++;
                }else if(rom[SPINE+4*rid+3]){cursor=++state[15];depth=1;}
            }
            for(int k=0;k<rule[2];k++){
                device const int *op=rom+rule[3]+5*k;
                for(int j=0;j<op[3];j++)args[j]=operand(rom[op[4]+j],env,lits);
                int kind=op[0],t=op[1],arity=op[3];
                if(kind==0){env[op[2]]=args[0];continue;}
                if(kind==3){long v;if(!prim(state,t,args[0],args[1],v)){state[5]=8;state[6]=rid;return;}env[op[2]]=v;continue;}
                if(kind==4){submit_union(state,meta,args[0],args[1]);if(state[5])return;continue;}
                if(kind==6){state[5]=10;state[6]=rid;return;}
                device const int *schema=table(rom,t);
                if(kind==2)arity--;
                for(int j=0;j<op[3];j++)if(schema[3]&(1<<j))args[j]=root_id(meta,int(args[j]));
                int found=find_key(rom,lits,meta,dyn,head,t,arity,args);
                if(kind==1){
                    if(found<0){args[arity]=long(NSYMBOLS+1+state[0]);found=insert_row(rom,state,meta,dyn,head,t,arity+1,args);}
                    if(found<0)return;publish_anchor(rom,state,meta,t,found,cursor,rid,depth);env[op[2]]=field(rom,lits,meta,dyn,found,arity);continue;
                }
                if(kind==5){
                    if(found>=0 && !meta[6*found+3]){meta[6*found+3]=1;meta[6*found+4]=run;state[8]=1;}
                    continue;
                }
                if(kind!=2){state[5]=11;state[6]=rid;return;}
                if(schema[1]){
                    if(found<0)found=insert_row(rom,state,meta,dyn,head,t,arity+1,args);
                    else submit_union(state,meta,field(rom,lits,meta,dyn,found,arity),args[arity]);
                    if(state[5])return;publish_anchor(rom,state,meta,t,found,cursor,rid,depth);
                    continue;
                }
                bool had_old=found>=0;long previous=0;
                if(found>=0){
                    long old=field(rom,lits,meta,dyn,found,arity),v=args[arity];
                    previous=old;v=merge_value(rom,lits,state,meta,dyn,head,t,old,v);
                    if(state[5]){state[6]=rid;return;}
                    if(old==v){publish_anchor(rom,state,meta,t,found,cursor,rid,depth);continue;}
                    if(meta[6*found+1]>=0){state[5]=13;state[6]=rid;return;}
                    dyn[found*WIDTH+arity]=v;meta[6*found+4]=run;state[8]=1;
                }else{found=insert_row(rom,state,meta,dyn,head,t,arity+1,args);if(found<0)return;}
                publish_anchor(rom,state,meta,t,found,cursor,rid,depth);
                log_write(state,writes,rid,state[9]-base_rhs-1,t,found,args,arity,had_old,previous,
                          field(rom,lits,meta,dyn,found,arity));if(state[5])return;
            }
        }
    }
    state[18]=1;repair(rom,lits,state,meta,dyn,head,writes);state[18]=0;if(state[5])return;
    if(state[8])state[2]++;
    device int *out=runs+(run-1)*6;out[0]=state[4];out[1]=state[9]-base_rhs;out[2]=state[10]-base_write;
    out[3]=state[8];out[4]=state[0];out[5]=state[2];state[11]=run;
}
kernel void export_rows(device const int *rom,device const long *lits,device const int *state,
                        device const int *meta,device const long *dyn,device long *out,uint id [[thread_position_in_grid]]){
    if(id>=uint(state[0]))return;
    for(int j=0;j<table(rom,meta[6*id])[0];j++)out[id*WIDTH+j]=field(rom,lits,meta,dyn,id,j);
}

kernel void next_run(device const int *rom,device int *state,device int *regs,device int *counts,uint gid [[thread_position_in_grid]]){ do_next_run(rom,state,regs,counts,gid); }

kernel void search(device const int *rom,device const long *lits,device int *state,
                   device const int *meta,device const long *dyn,device const int *head,
                   device const int *wm,device int *count,device long *tok,constant int &lanes,
                   uint gid [[thread_position_in_grid]]){ do_search(rom,lits,state,meta,dyn,head,wm,count,tok,lanes,gid); }

kernel void commit(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head,device int *wm,device const int *count,device long *tok,
                   device long *rhs,device long *writes,device int *runs,device int *resumes,constant int &lanes,
                   uint gid [[thread_position_in_grid]]){ do_commit(rom,lits,state,meta,dyn,head,wm,count,tok,rhs,writes,runs,resumes,lanes,gid); }

kernel void run_batch(device const int *rom,device const long *lits,device int *state,device int *regs,
                      device int *meta,device long *dyn,device int *head,device int *wm,device int *count,device long *tok,
                      device long *rhs,device long *writes,device int *runs,device int *resumes,
                      constant int &lanes,constant int &budget,uint gid [[thread_position_in_threadgroup]],
                      uint group [[threads_per_threadgroup]]){
    for(int i=0;i<budget;i++){
        if(SHARED_ARENA)for(uint j=gid;j<2*RULES;j+=group)count[j]=0;
        do_next_run(rom,state,regs,count,gid);threadgroup_barrier(mem_flags::mem_device);
        if(state[5]||state[7])return;
        int work=rom[SETS+2*state[4]]*PARTS;
        for(uint task=gid;task<uint(work);task+=group)
            do_search(rom,lits,state,meta,dyn,head,wm,count,tok,lanes,task);
        threadgroup_barrier(mem_flags::mem_device);
        do_commit(rom,lits,state,meta,dyn,head,wm,count,tok,rhs,writes,runs,resumes,lanes,gid);
        threadgroup_barrier(mem_flags::mem_device);
    }
}

kernel void export_roots(device const int *meta,device int *roots,uint id [[thread_position_in_grid]]){
    roots[id]=root_id(meta,int(id));
}
