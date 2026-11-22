#include <metal_stdlib>
#ifndef CAPTURE_BOUNDARIES
#define CAPTURE_BOUNDARIES 0
#endif
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
inline void count_work(device int *state,int i,int value){
    if(COUNT_WORK)atomic_fetch_add_explicit((device atomic_int *)(state+51+i),value,memory_order_relaxed);
}
inline int root_id(device const int *meta,int v){
    device const int *parent=meta+6*ROW_CAP;
    while(parent[v])v=parent[v];
    return v;
}
#if HAS_SETS
// 63 immutable element slots. The second array maps each slot to its current
// canonical bit. Only ordered commit changes parents or alias forwarding.
inline int set_element(device const int *meta,int i){
    return atomic_load_explicit((device const atomic_int *)(meta+SET_BASE+i),memory_order_relaxed);
}
inline ulong normalized_mask_once(device const int *meta,ulong mask){
    ulong result=0;
    while(mask){int i=ctz(mask);mask&=mask-1;result|=1UL<<meta[SET_BASE+63+i];}
    return result;
}
inline int member_bit(device const int *meta,device int *state,int value){
    if(value<=0 || value>=UF_SIZE){state[5]=20;return -1;}
    int root=root_id(meta,value);
    for(int i=0;i<63;i++){
        int raw=set_element(meta,i);
        if(!raw){
            int empty=0;
            device atomic_int *slot=(device atomic_int *)(const_cast<device int *>(meta)+SET_BASE+i);
            while(!atomic_compare_exchange_weak_explicit(slot,&empty,root,memory_order_relaxed,memory_order_relaxed) && !empty){}
            raw=empty?empty:root;
        }
        if(root_id(meta,raw)==root)return meta[SET_BASE+63+i];
    }
    state[5]=20;return -1;
}
inline void set_count(device int *state,int n){
    if(COUNT_WORK)atomic_fetch_add_explicit((device atomic_int *)(state+56+n),1,memory_order_relaxed);
}
inline void repair_set_aliases_once(device int *meta,device int *state,int hi,int lo){
    int first=-1;
    for(int i=0;i<63;i++){
        int raw=set_element(meta,i);if(!raw)break;
        if(root_id(meta,raw)!=lo)continue;
        if(first<0)first=i;
        if(meta[SET_BASE+63+i]!=first){meta[SET_BASE+63+i]=first;set_count(state,6);}
    }
}
inline bool set_changed_once(device const int *meta,ulong mask,int epoch){
    while(mask){int bit=ctz(mask);mask&=mask-1;
        for(int v=set_element(meta,bit);meta[6*ROW_CAP+v];v=meta[6*ROW_CAP+v])
            if(meta[6*ROW_CAP+UF_SIZE+v]==epoch)return true;
    }
    return false;
}
// Diagnostic paired amplification. Each operation still executes once on
// live state. Volatile inputs keep the replicated reads inside the kernel.
inline ulong normalized_mask(device const int *meta,ulong mask){
    ulong result=normalized_mask_once(meta,mask);
#if SET_MAINT_REPEAT>1
    volatile ulong input=mask,sink=0;
    for(int j=1;j<SET_MAINT_REPEAT;j++){
        ulong x=input;sink=SET_MAINT_CONTROL?x:normalized_mask_once(meta,x);
    }
#endif
    return result;
}
inline bool set_changed(device const int *meta,ulong mask,int epoch){
    bool result=set_changed_once(meta,mask,epoch);
#if SET_MAINT_REPEAT>1
    volatile ulong input=mask,sink=0;
    for(int j=1;j<SET_MAINT_REPEAT;j++){
        ulong x=input;sink=SET_MAINT_CONTROL?x:ulong(set_changed_once(meta,x,epoch));
    }
#endif
    return result;
}
inline void repair_set_aliases(device int *meta,device int *state,int hi,int lo){
    repair_set_aliases_once(meta,state,hi,lo);
#if SET_MAINT_REPEAT>1
    volatile int input=lo,sink=0;
    for(int j=1;j<SET_MAINT_REPEAT;j++){
        int x=input;sink=x;if(!SET_MAINT_CONTROL)repair_set_aliases_once(meta,state,hi,x);
    }
#endif
}
inline int take_min_member(device const int *meta,thread ulong &mask){
    int smallest=INT_MAX,slot=-1;
    for(ulong m=mask;m;m&=m-1){
        int i=ctz(m),v=root_id(meta,set_element(meta,i));
        if(v<smallest){smallest=v;slot=i;}
    }
    mask&=~(1UL<<slot);return smallest;
}
#endif
#if BLOCK_STUDY
inline void study_add(device int *s,int index,int n=1){
    if(COUNT_WORK)atomic_fetch_add_explicit((device atomic_int *)(s+index),n,memory_order_relaxed);
}
#endif
// REGION_DEVICE_FUNCTIONS
#if INDEX_NOTIFY
// A constructor's direct fields never lose a dependency except by retirement
// or union. Moving (and retaining) reverse bits is conservative across both.
// Uncovered functions/tables always stay in the ordinary ordered scan.
constant int ROW_WORDS=ROW_CAP/32;
constant int NOTIFY_BASE=TABLES*((USE_INDEX?257:1)+((TILES>1||LEARN_OWNER)?PARTS:0)+(HOT_FILTER>0)+((HOT_FILTER==2||HOT_FILTER==3)?PARTS:0));
#if CO_SPARSE_WORDS
constant int SUMMARY_WORDS=(ROW_WORDS+31)/32;
inline device uint *active_words(device uint *bits,int root){
    return bits+(2+UF_SIZE)*ROW_WORDS+root*SUMMARY_WORDS;
}
#endif
// CO_REPAIR_DEVICE_FUNCTIONS
inline void subscribe_row(device const int *rom,device const long *lits,device int *meta,device long const *dyn,
                          device int *head,device int *state,int row,int t){
#if REGION_SELECT
    region_add(rom,lits,meta,dyn,head,state,row,t);return;
#endif
    device uint *bits=(device uint *)(head+NOTIFY_BASE);
    uint mask=1u<<(row%32);int word=row/32;
    if(repair_shapes[t]<0){bits[word]|=mask;return;}
#if CO_MODE
    int owner=co_owner(rom,lits,meta,dyn,state,row,t);
    mask=1u<<(owner%32);word=owner/32;
#endif
    device const int *spec=table(rom,t);
    for(int j=0;j<spec[0];j++)if(spec[3]&(1<<j)){
        int v=root_id(meta,int(rawfield(rom,lits,meta,dyn,row,j)));
        bits[(2+v)*ROW_WORDS+word]|=mask;study_add(state,73);
#if CO_SPARSE_WORDS
        active_words(bits,v)[word/32]|=1u<<(word%32);
        co_count(state,15);
#endif
    }
}
inline void notify_roots(device int *meta,device int *head,device int *state,int hi,int lo){
#if REGION_SELECT
    region_notify(meta,head,state,hi,lo);return;
#endif
    device uint *bits=(device uint *)(head+NOTIFY_BASE);
    int end=(state[0]+31)/32;
    for(int w=0;w<end;w++){
#if CO_SPARSE_WORDS
        co_count(state,14);
        uint present=active_words(bits,hi)[w/32] & (~0u<<(w%32));
        if(!present){w=(w/32+1)*32-1;continue;}
        w=(w/32)*32+ctz(present);
#endif
        uint affected=bits[(2+hi)*ROW_WORDS+w];
        if(affected){
#if CO_MODE
            uint rows=co_notify(meta,bits+ROW_WORDS,state,w,affected,hi,lo);
#else
            uint rows=affected;
#endif
            bits[ROW_WORDS+w]|=rows;bits[(2+lo)*ROW_WORDS+w]|=affected;
#if CO_SPARSE_WORDS
            active_words(bits,lo)[w/32]|=1u<<(w%32);
            co_count(state,15);
#endif
        }
        if(COUNT_WORK)state[74]++;
    }
}
#endif
inline bool unite(device int *state,device int *meta,long a,long b,device int *head){
    if(a<=0 || b<=0 || a>=UF_SIZE || b>=UF_SIZE){state[5]=14;return false;}
    int x=root_id(meta,int(a)),y=root_id(meta,int(b));
    if(x==y)return false;
    int hi=max(x,y),lo=min(x,y);
    int log=state[14]++;
    if(log>=UF_SIZE){state[5]=17;return false;}
    device int *u=meta+UNION_LOG+4*log;
    u[0]=state[3];u[1]=state[0];u[2]=hi;u[3]=lo;
#if INDEX_NOTIFY
    notify_roots(meta,head,state,hi,lo);
#endif
    meta[6*ROW_CAP+hi]=lo;
    #if HAS_SETS
    repair_set_aliases(meta,state,hi,lo);
#endif
    meta[6*ROW_CAP+UF_SIZE+hi]=state[3];state[8]=1;state[12]=1;
    return true;
}
// The source queues explicit RHS unions until all matches of this Run commit.
inline void submit_union(device int *state,device int *meta,long a,long b,device int *head){
#if FENCE_UNIONS
    int n=state[13];if(n>=TRACE_CAP){state[5]=16;return;}
    device int *queue=meta+6*ROW_CAP+2*UF_SIZE;
    queue[2*n]=int(a);queue[2*n+1]=int(b);state[13]++;
#else
    unite(state,meta,a,b,head);
#endif
}
inline long field(device const int *rom,device const long *lits,device const int *meta,
                  device const long *dyn,int row,int col){
    long v=rawfield(rom,lits,meta,dyn,row,col);
#if HAS_SETS
    if(rom[SET_COLS+meta[6*row]]&(1<<col))return long(normalized_mask(meta,ulong(v)));
#endif
    return (table(rom,meta[6*row])[3]&(1<<col))?long(root_id(meta,int(v))):v;
}
constant int SHARD_NEXT=BIRTH_RUN+8*ROW_CAP;
constant int SHARD_HEAD=TABLES*(1+256*USE_INDEX);
constant int ROW_OWNER=SHARD_NEXT+ROW_CAP;
inline int shard_of(device const int *meta,int row){return LEARN_OWNER?meta[ROW_OWNER+row]:row%PARTS;}
// Conservative upper bounds, never reset on retirement. Every write to a
// row's matching epoch must also update its table and (when enabled) shard.
constant int HIGH_WATER=SHARD_HEAD+((TILES>1 || LEARN_OWNER)?TABLES*PARTS:0);
#if BLOCK_STUDY
// One persistent cursor list per table/shard; a refresh moves a row to the
// front. Its time is an upper bound on the row epoch, so a tail can stop
// early. A newer publication alone never makes an old fact match.
inline void refresh_cursor(device int *meta,device int *state,int t,int row,int epoch){
    if(!SELECT_BLOCKS || !bake_tables[t])return;
    device int *stamp=meta+BLOCK_BASE,*next=stamp+ROW_CAP,*prev=next+ROW_CAP;
    device int *head=prev+ROW_CAP+t*PARTS+shard_of(meta,row);
    if(stamp[row]==epoch)return;
    if(stamp[row]){
        if(prev[row])next[prev[row]-1]=next[row];else *head=next[row];
        if(next[row])prev[next[row]-1]=prev[row];
    }
    stamp[row]=epoch;prev[row]=0;next[row]=*head;
    if(*head)prev[*head-1]=row+1;
    *head=row+1;study_add(state,77);
}
#endif
inline void touch_row(device int *state,device int *meta,device int *head,int row,int t,int epoch){
    meta[6*row+4]=epoch;
#if BLOCK_STUDY
    if(meta[BIRTH_RUN+ROW_CAP+5*row])refresh_cursor(meta,state,t,row,epoch);
#endif
    if(HOT_FILTER)head[HIGH_WATER+t]=epoch;
    if((HOT_FILTER==2 || HOT_FILTER==3))head[HIGH_WATER+TABLES+t*PARTS+shard_of(meta,row)]=epoch;
}
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
#if HAS_SETS
    for(int i=0;i<63;i++){meta[SET_BASE+i]=i<NSET_SEEDS?rom[SET_SEEDS+i]:0;meta[SET_BASE+63+i]=i;}
#endif
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
            m[0]=t;m[1]=cell;m[2]=j;m[3]=(inst[2]>>j)&1;m[4]=0;m[5]=head[t];head[t]=id;
#if INDEX_NOTIFY
            subscribe_row(rom,lits,meta,dyn,head,state,id,t);
#endif
            append_shard(rom,meta,head,id,t,(LEARN_OWNER && table(rom,t)[0]>1)?rawfield(rom,lits,meta,dyn,id,0):0);
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
inline bool eval_op(device int *state,device const int *meta,int op,
                    device const int *args,int n,thread long *env,device const long *lits,thread long &out){
#if HAS_SETS
    if(op>=16){
        set_count(state,op-16);
        ulong a=0,b=0;
        if(op>=18)a=normalized_mask(meta,ulong(operand(args[0],env,lits)));
        if(op==19 || op==20)b=normalized_mask(meta,ulong(operand(args[1],env,lits)));
        if(op==16)out=0;
        else if(op==17 || op==18){
            for(int j=op==18?1:0;j<n;j++){
                int slot=member_bit(meta,state,int(operand(args[j],env,lits)));
                if(slot<0)return false;
                a|=1UL<<slot;
            }
            out=long(a);
        }else if(op==19)out=long(a&b);
        else if(op==20)out=long(a|b);
        else if(op==21)out=long(popcount(a));
        else return false;
        return true;
    }
#endif
    return prim(state,op,operand(args[0],env,lits),operand(args[1],env,lits),out);
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
#if COMPOUND
struct CompoundClaim {int parent,join,ordinal,row,ticket,verified,bank,winner,status,attempts,next;};
inline device CompoundClaim *claims(device int *meta){return reinterpret_cast<device CompoundClaim *>(meta+COM_RECORDS);}
inline device const CompoundClaim *claims(device const int *meta){return reinterpret_cast<device const CompoundClaim *>(meta+COM_RECORDS);}
// Bind named side ports when the producer returns its actual pivot, before
// the consumer Run. Only unique point keys derived from that pivot are legal.
#if COM_BOUNDARY_WIDTH
inline void bind_side_ports(device const int *rom,device const long *lits,device int *meta,
                            device const long *dyn,device const int *head,int id){
    device CompoundClaim &claim=claims(meta)[id];
    constant int *entry=neural_catalog+4*compound_joins[4*claim.join+3];
    int atoms=rom[RULE+7*entry[0]];
    if(atoms<=1)return;
    long values[MAXSLOTS];bool bound[MAXSLOTS]={false};
    for(int pos=0;pos<atoms;pos++){
        device const int *op=rom+entry[2]+4*pos,*args=rom+op[2];
        int table_id=op[0],arity=op[1],row=claim.row;
        if(table_id<0)continue;
        if(pos){
            long key[WIDTH];
            for(int j=0;j<arity-1;j++){
                if(args[j]>=0 && !bound[args[j]])return;
                key[j]=operand(args[j],values,lits);
            }
            meta[COM_BOUNDARY_STATS]++;
            row=find_key(rom,lits,meta,dyn,head,table_id,arity-1,key);
            if(row<0 || meta[6*row+3])return;
            device int *ref=meta+COM_BOUNDARIES+2*(id*COM_BOUNDARY_WIDTH+pos-1);
            ref[0]=row+1;ref[1]=meta[6*row+4];
        }
        for(int j=0;j<arity;j++)if(args[j]>=0 && (op[3]&(1<<j))){
            values[args[j]]=field(rom,lits,meta,dyn,row,j);bound[args[j]]=true;
        }
    }
}
#endif
#endif
inline void publish_anchor(device const int *rom,device int *state,device int *meta,int t,int row,
                           int root,int producer,int depth,device int *pending=nullptr,int effect=-1,device const long *lits=nullptr,
                           device const long *dyn=nullptr,device const int *head=nullptr){
    if(!SPINE_ON || row<0 || !root || !rom[DEMANDED+t])return;
    if(pending){
        int n=pending[0]++;
        if(n>=TRACE_CAP){state[5]=19;return;}
        device int *e=pending+1+5*n;e[0]=t;e[1]=row;e[2]=root;e[3]=producer;e[4]=depth;
        return;
    }
    device int *h=anchor(meta,row);
#if NEURAL_EDGES
    if(state[17]>=TRACE_CAP || effect<0){state[5]=19;return;}
    device int *pub=meta+EDGE_PUBLISHED+4*state[17];
    pub[0]=state[9];pub[1]=effect;pub[2]=row;pub[3]=t;
#endif
    h[0]=root;h[1]=producer;h[2]=depth;h[3]=state[3];h[4]=++state[17];
#if COMPOUND
    if(state[76])for(int lane=0;lane<2;lane++){
        int id=(state[3]-1)*2+lane;device CompoundClaim &c=claims(meta)[id];
        if(c.status!=1 || c.parent+1!=state[76])continue;
        constant int *link=compound_joins+4*c.join;
        if(link[2]!=effect || neural_catalog[4*link[3]+3]!=t)continue;
        c.ordinal=state[9];c.row=row;c.ticket=h[4];c.status=2;
        meta[COM_QUEUE+state[75]++]=id;
#if COM_BOUNDARY_WIDTH
        bind_side_ports(rom,lits,meta,dyn,head,id);
#endif
    }
#ifdef COM_TAIL_BASE
    if(state[77]){
        int origin=state[77]-1;
        int tail=compound_tails[claims(meta)[origin].join];
        constant int *link=compound_joins+4*tail;
        int id=COM_TAIL_BASE+origin;
        device CompoundClaim &c=claims(meta)[id];
        if(!c.status && link[2]==effect && neural_catalog[4*link[3]+3]==t){
            c.join=tail;c.parent=origin;c.ordinal=state[9];c.row=row;c.ticket=h[4];c.status=2;
            meta[COM_QUEUE+state[75]++]=id;
#if COM_BOUNDARY_WIDTH
            bind_side_ports(rom,lits,meta,dyn,head,id);
#endif
        }
    }
#endif
#endif
#if BLOCK_STUDY
    refresh_cursor(meta,state,t,row,state[3]);
#endif
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
#if CAPTURE_BOUNDARIES
inline void capture_inputs(device const int *meta,int rid,int pos,int n,thread int *witness){
    device int *record=const_cast<device int *>(meta)+BOUNDARY_MATCH+3*DEPTH*(rid*2*TOKEN_CAP+pos);
    for(int k=0;k<n;k++){
        int row=witness[k];
        record[3*k]=row+1;
        record[3*k+1]=row<0?0:meta[6*row+4];
        record[3*k+2]=row<0?0:anchor(meta,row)[4];
    }
}
#endif
template<bool CERT=false,bool ONE=false>
inline void route(device int *state,device const int *rom,device const long *lits,device const int *meta,
                  device const long *dyn,device const int *head,device const int *rule,
                  device const int *path,int pivot,int last,int lane,int lanes,
                  device int *cnt,device long *bank,device int *certs,int requested=-1,device const int *named=nullptr){
    int table0=path[0];
    int first=(TILES>1 || LEARN_OWNER)?head[SHARD_HEAD+table0*PARTS+lane]:head[table0];
#if BLOCK_STUDY
    int rid=int((rule-rom-RULE)/7),leaf=bake_pivots[rid*DEPTH+pivot];
    bool indexed=SELECT_BLOCKS && leaf>=0;
    if(indexed){first=meta[BLOCK_BASE+3*ROW_CAP+table0*PARTS+lane]-1;study_add(state,78);}
#endif
    if(ONE)first=requested;
    for(int seed=first;seed>=0;seed=ONE?-1:
#if BLOCK_STUDY
        indexed?meta[BLOCK_BASE+ROW_CAP+seed]-1:
#endif
        (TILES>1 || LEARN_OWNER)?meta[SHARD_NEXT+seed]:meta[6*seed+5]){
        device const int *h=anchor(meta,seed);
#if BLOCK_STUDY
        study_add(state,79);
        if(leaf>=0)study_add(state,88+LIBRARY_SIZE+leaf);
        if(indexed && meta[BLOCK_BASE+seed]<last)break;
#endif
#if NEURAL_ACTIVE
        if(!ONE && NEURAL_CLOSE){
            bool closed=false;
            for(int n=0;n<NEURAL_SLOTS;n++){
                device const int *mark=meta+NEURAL_BASE+4*n;
                if(mark[0]==int((rule-rom-RULE)/7) && mark[1]==pivot && mark[2]==seed){
                    closed=true;break;
                }
            }
#if COMPOUND
            device const int *index=meta+COM_HEAD+2*seed;
            if(index[0]==state[3])for(int id=index[1]-1;id>=0;id=claims(meta)[id].next-1){
                constant int *e=neural_catalog+4*compound_joins[4*claims(meta)[id].join+3];
                closed|=e[0]==int((rule-rom-RULE)/7) && e[1]==pivot;
            }
#endif
            if(closed){
                if(COUNT_WORK)atomic_fetch_add_explicit((device atomic_int *)(state+69),1,memory_order_relaxed);
                continue;
            }
        }
#endif
        if(shard_of(meta,seed)!=lane || meta[6*seed+3] || !h[0] || meta[6*seed+4]<last)continue;
#if BLOCK_STUDY
        if(leaf>=0)study_add(state,88+2*LIBRARY_SIZE+leaf);
#endif
        long env[MAXSLOTS];int witness[DEPTH];bool matched=true;
        for(int pos=0;pos<rule[0] && matched;pos++){
#if NEURAL_ACTIVE
            if(COUNT_WORK)atomic_fetch_add_explicit((device atomic_int *)(state+(ONE?70:71)),1,memory_order_relaxed);
#endif
            device const int *op=path+4*pos,*args=rom+op[2];int t=op[0],n=op[1],row=seed;
            if(t<0){
                long v=0;matched=eval_op(state,meta,-1-t,args,n-1,env,lits,v);
                if(CERT || CAPTURE_BOUNDARIES)witness[pos]=-1;
                if(op[3]&(1<<(n-1)))env[args[n-1]]=v;
                else matched &= operand(args[n-1],env,lits)==v;
            }else{
                if(pos){
#if NEURAL_ACTIVE
                    if(COUNT_WORK)atomic_fetch_add_explicit((device atomic_int *)(state+(ONE?72:73)),1,memory_order_relaxed);
#endif
                    if(named){
#if COM_BOUNDARY_WIDTH
                        const_cast<device int *>(meta)[COM_BOUNDARY_STATS+1]++;
#endif
                        row=named[2*(pos-1)]-1;
                        if(row<0 || meta[6*row]!=t || meta[6*row+4]!=named[2*(pos-1)+1]){
                            matched=false;break;
                        }
                    }else{
                        long key[WIDTH];for(int j=0;j<n-1;j++)key[j]=operand(args[j],env,lits);
                        row=find_key(rom,lits,meta,dyn,head,t,n-1,key);
                    }
                    if(row<0 || meta[6*row+3]){matched=false;break;}
                }
                if(CERT || CAPTURE_BOUNDARIES)witness[pos]=row;
                for(int j=0;j<n;j++){
                    long v=field(rom,lits,meta,dyn,row,j);
                    if(op[3]&(1<<j))env[args[j]]=v;
                    else if(operand(args[j],env,lits)!=v){matched=false;break;}
                }
            }
        }
        if(!matched)continue;
#if NEURAL_LABELS
        // Diagnostic labels are written only after a real certified path succeeds.
        // The features bank consumed by the actor cannot address this storage.
        for(int l=0;l<NEURAL_LEAVES;l++){
            if(neural_catalog[4*l]!=int((rule-rom-RULE)/7) || neural_catalog[4*l+1]!=pivot)continue;
            int k=0;for(int r=head[table0];r>=0 && k<NEURAL_RANKS;r=meta[6*r+5],k++){
                if(r==seed){
                    device int *labels=const_cast<device int *>(meta)+NEURAL_BASE+TRACE_CAP+(state[3]-1)*NEURAL_ACTIONS;
                    labels[l*NEURAL_RANKS+k]=1;break;
                }
            }
        }
#endif
        int j=reserve_token(cnt);if(j<0)return;
        if(CERT){
            device int *dst=certs+j*(DEPTH+3);
            dst[0]=int(path-rom);dst[1]=seed;dst[2]=pivot;
            for(int k=0;k<rule[0];k++)dst[3+k]=witness[k];
            continue;
        }
#if CAPTURE_BOUNDARIES
        capture_inputs(meta,int((rule-rom-RULE)/7),j,rule[0],witness);
#endif
        int width=input_width(rule);device long *out=bank+j*(width+5);
        for(int k=0;k<rule[4];k++)out[k]=env[rom[rule[5]+k]];
        out[width]=seed;out[width+1]=h[0];out[width+2]=h[1];out[width+3]=h[2];
        out[width+4]=long((table(rom,table0)[1]?0:ROW_CAP)+seed)*DEPTH+pivot;
    }
}
// NEURAL_DEVICE_KERNELS
template<int PART=0,bool CERT=false>
inline void do_search(device const int *rom,device const long *lits,device int *state,
                   device const int *meta,device const long *dyn,device const int *head,
                   device const int *wm,device int *count,device long *tok,constant int &lanes,
                   uint gid,device int *certs=nullptr){
    if(state[5]||state[7])return;
    device const int *rs=rom+SETS+2*state[4];int idx=gid/PARTS,lane=gid%PARTS;
    if(idx>=rs[0])return;
    count_work(state,0,1);
    int r=rom[rs[1]+idx];device const int *rule=rom+RULE+7*r;
#if NEURAL_BOOTSTRAP_ONLY
    if(rule[0]!=0)return;
#endif
    int bank=SHARED_ARENA?2*r:r*PARTS+lane;if(!SHARED_ARENA)count[bank]=0;
    int width=input_width(rule);device long *target=tok+token_offset(rom,r)+(SHARED_ARENA?0:lane)*TOKEN_CAP*(width+5);
    int q=rule[0],pivot=-1,last=wm[r],last_fresh=-1;
    for(int j=0;j<q;j++){int t=rom[rule[1]+4*j];if(t>=0){if(pivot<0)pivot=j;if(head[t]<0)return;
        if(HOT_FILTER && head[HIGH_WATER+t]>=last)last_fresh=j;
    }}
    if(HOT_FILTER && rule[6] && last>0 && pivot>=0 && last_fresh<0){count_work(state,1,1);return;}
    if((HOT_FILTER==2 || HOT_FILTER==3) && rule[6] && last>0 && pivot==last_fresh && pivot>=0){
        int t=rom[rule[1]+4*pivot];
        if(head[HIGH_WATER+TABLES+t*PARTS+lane]<last){count_work(state,2,1);return;}
    }
    if(pivot<0 && lane)return;
    if(q==0 && rule[6] && last>=0)return;
    device const int *sp=rom+SPINE+4*r;
    if(SPINE_ON && PART!=1)for(int k=0;k<sp[0];k++){
        device const int *e=rom+sp[1]+2*k;
        if(HOT_FILTER && head[HIGH_WATER+rom[e[1]]]<last)continue;
        if((HOT_FILTER==2 || HOT_FILTER==3) && head[HIGH_WATER+TABLES+rom[e[1]]*PARTS+lane]<last)continue;
        route<CERT>(state,rom,lits,meta,dyn,head,rule,rom+e[1],e[0],last,lane,PARTS,count+bank,target,CERT?certs+r*(2*TOKEN_CAP)*(DEPTH+3):nullptr);
        if(!SHARED_ARENA && count[bank]<0)return;
    }
    if(PART==2)return;
    bool routed[DEPTH];routed[0]=false;
    long env[MAXSLOTS];int cur[DEPTH],epoch[DEPTH],witness[DEPTH];cur[0]=-2;epoch[0]=0;
#if BLOCK_STUDY
    int owner[DEPTH];owner[0]=-1;
#endif
    int depth=0,visits=0;
    while(depth>=0){
#if BLOCK_STUDY
        int next_owner=owner[depth];
        if(next_owner>=0)study_add(state,88+next_owner);
#endif
        if(++visits>SEARCH_CAP){token_error(count+bank,-1);return;}
        if(depth==q){
            if(!routed[depth] && (!rule[6] || epoch[depth]>=last)){
                int pos=reserve_token(count+bank);if(pos<0)return;
                if(CERT){
                    device int *dst=certs+(r*2*TOKEN_CAP+pos)*(DEPTH+3);
                    dst[0]=-1;dst[1]=pivot>=0?witness[pivot]:-1;dst[2]=0;
                    for(int k=0;k<q;k++)dst[3+k]=witness[k];
                    depth--;continue;
                }
#if CAPTURE_BOUNDARIES
                capture_inputs(meta,r,pos,q,witness);
#endif
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
            if(CERT || CAPTURE_BOUNDARIES)witness[depth]=-1;
            cur[depth]=-1;long val=0;
            ok=eval_op(state,meta,-1-t,args,op[1]-1,env,lits,val);
            int lastcol=op[1]-1,key=args[lastcol];
            if(op[3]&(1<<lastcol))env[key]=val;
            else ok &= operand(key,env,lits)==val;
        }else{
            device const int *m=meta+6*row;cur[depth]=point?-1:(((TILES>1 || LEARN_OWNER) && depth==pivot)?meta[SHARD_NEXT+row]:m[5]);
            if(m[3] || (depth==pivot && shard_of(meta,row)!=lane))continue;
            if((HOT_FILTER==2 || HOT_FILTER==4) && rule[6] && depth==last_fresh && version<last && m[4]<last)continue;
            // A certified functional continuation owns every suffix from this
            // specific published witness. Other pivots remain in the residual join.
#if BLOCK_STUDY
            int leaf=bake_entries[r*DEPTH+depth];
            if(leaf>=0 && next_owner<0 && SPINE_ON && (sp[2]&(1<<depth)) && m[4]>=last && anchor(meta,row)[0]){
                // The routed solver still does the key reads, version checks
                // and ordered publication. Only redundant residual work goes.
                study_add(state,69);
                if(SELECT_BLOCKS)continue;
                next_owner=leaf;
            }
#endif
            if(PRUNE_ROUTED && SPINE_ON && (sp[2]&(1<<depth)) && m[4]>=last && anchor(meta,row)[0])continue;
            for(int j=0;j<op[1];j++){
                long v=field(rom,lits,meta,dyn,row,j);int key=args[j];
                if(op[3]&(1<<j))env[key]=v;
                else if(operand(key,env,lits)!=v){ok=false;break;}
            }
            version=max(version,m[4]);witness[depth]=row;
        }
        if(ok){
#if BLOCK_STUDY
            owner[depth+1]=next_owner;
#endif
            routed[depth+1]=routed[depth] || (SPINE_ON && t>=0 && (sp[2]&(1<<depth)) && meta[6*row+4]>=last && anchor(meta,row)[0]);
            depth++;epoch[depth]=version;cur[depth]=-2;}
    }
    count_work(state,3,visits);
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
    state[0]++;device int *m=meta+6*id;m[0]=t;m[1]=-1;m[2]=0;m[3]=0;m[5]=head[t];head[t]=id;append_shard(rom,meta,head,id,t,n>1?values[0]:0);touch_row(state,meta,head,id,t,state[3]);
    meta[BIRTH_RUN+id]=state[18]?-state[3]:state[3];
    for(int j=0;j<n;j++){
        dyn[id*WIDTH+j]=values[j];
#if PUBLISHED_KEYS
        if(j<n-1)dyn[(ROW_CAP+id)*WIDTH+j]=values[j];
#endif
    }
#if INDEX_NOTIFY
    subscribe_row(rom,nullptr,meta,dyn,head,state,id,t);
#endif
    if(USE_INDEX)link_key(meta,head,id,t,key_bucket(values,n-1));
    state[8]=1;return id;
}
inline int compare(device const long *a,device const long *b,int n,device const int *rom,device const int *meta,int rid){
    for(int j=0;j<n;j++){
        if(a[j]==b[j])continue;
#if HAS_SETS
        if(rom[SET_INPUTS+rid]&(1<<j)){
            ulong x=ulong(a[j]),y=ulong(b[j]);
            while(x && y){int l=take_min_member(meta,x),r=take_min_member(meta,y);if(l!=r)return l<r?-1:1;}
            if(x || y)return x?1:-1;
            continue;
        }
#endif
        return a[j]<b[j]?-1:1;
    }
    return 0;
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
    for(int j=0;j<state[13];j++)unite(state,meta,queue[2*j],queue[2*j+1],head);
    state[13]=0;
#endif
    int passes=0;
    while(state[12] && !state[5]){
#if REGION_SELECT || REGION_CAPTURE
        state[REG_COUNTER]++;
#endif
        if(++passes>ROW_CAP){state[5]=15;return;}
        state[12]=0;
        for(int row=0;row<state[0];row++){
#if INDEX_NOTIFY
            // Consume in original physical order. Re-read the current word
            // after each affected row because a collision can add later rows.
            int w=row/32;
            device uint *bits=(device uint *)(head+NOTIFY_BASE);
            uint mask=(bits[w]|bits[ROW_WORDS+w]) & (~0u<<(row%32));
            if(COUNT_WORK)state[75]++;
            if(!mask){row=32*w+31;continue;}
            row=32*w+ctz(mask);
            if(row>=state[0])break;
#endif
            device int *m=meta+6*row;if(m[3]==2)continue;
            int t=m[0];device const int *spec=table(rom,t);int last=spec[0]-1;
            count_work(state,4,1);
            bool changed=false,key_changed=false;
#if CO_MODE==3
            if(meta[CO_EPOCH+row]==state[3] && meta[CO_JOIN+row]!=state[3]){
                int ports=meta[CO_PORTS+row];
                changed=ports!=0;key_changed=(ports&((1<<last)-1))!=0;
                co_count(state,6);
                if(!key_changed)co_count(state,13);
            }else
#endif
            for(int j=0;j<=last;j++)if(spec[3]&(1<<j)){
                int v=int(rawfield(rom,lits,meta,dyn,row,j));
                while(meta[6*ROW_CAP+v]){
                    if(meta[6*ROW_CAP+UF_SIZE+v]==state[3]){changed=true;key_changed|=j<last;}
                    v=meta[6*ROW_CAP+v];
                }
            }
#if HAS_SETS
            for(int j=0;j<=last;j++)if(rom[SET_COLS+t]&(1<<j)){
                set_count(state,7);
                if(set_changed(meta,ulong(rawfield(rom,lits,meta,dyn,row,j)),state[3])){
                    changed=true;key_changed|=j<last;set_count(state,8);
                }
            }
#endif
#if BLOCK_STUDY
            if(repair_shapes[t]>=0){
#if REGION_SELECT || REGION_CAPTURE
                meta[REG_CHANGES+row/32]+=int(changed);
#if REGION_CAPTURE
                meta[REG_PAYLOAD+8*(((state[3]-1)/REG_WINDOW)*REG_WORDS+row/32)+6+int(changed)]++;
#endif
#endif
                if(COUNT_WORK){
                    state[70]++;
                    state[88+3*LIBRARY_SIZE+2*repair_shapes[t]+int(changed)]++;
                }
                if(COUNT_WORK && changed){state[71]++;state[72]+=int(key_changed);}
            }else {if(COUNT_WORK)state[76]++;}
#endif
            if(!changed)continue;
            touch_row(state,meta,head,row,t,state[3]);if(!key_changed)continue;
#if CO_MODE
            co_count(state,7);
#endif
            long key[WIDTH];
            for(int j=0;j<last;j++)key[j]=field(rom,lits,meta,dyn,row,j);
            int start=INDEX_REPAIR?head[TABLES+t*256+key_bucket(key,last)]:head[t];
            for(int other=start;other>=0;other=INDEX_REPAIR?meta[INDEX_NEXT+other]:meta[6*other+5]){
                if(other==row || meta[6*other+3]==2)continue;
#if CO_MODE
                co_count(state,8);
#endif
                bool same=true;for(int j=0;j<last;j++)if(key[j]!=directory_key(rom,lits,meta,dyn,other,j)){same=false;break;}
                if(!same)continue;
#if CO_MODE
                co_count(state,9);
#endif
                int keep=PUBLISHED_KEYS?other:min(row,other),drop=PUBLISHED_KEYS?row:max(row,other);
                long old=field(rom,lits,meta,dyn,keep,last),v=field(rom,lits,meta,dyn,drop,last);
                if(spec[1])unite(state,meta,old,v,head);
                else{
                    long next=merge_value(rom,lits,state,meta,dyn,head,t,old,v);
                    if(next!=old){if(meta[6*keep+1]>=0){state[5]=13;return;}log_write(state,writes,-1,-1,t,keep,key,last,true,old,next);dyn[keep*WIDTH+last]=next;touch_row(state,meta,head,keep,t,state[3]);}
                }
                if(meta[6*drop+3]==1){meta[6*keep+3]=1;touch_row(state,meta,head,keep,t,state[3]);}
                if(SPINE_ON){
                    device int *lost=anchor(meta,drop),*saved=anchor(meta,keep);
                    if(lost[3]==state[3] && lost[4]>saved[4]){
                        for(int j=0;j<5;j++)saved[j]=lost[j];
#if BLOCK_STUDY
                        refresh_cursor(meta,state,t,keep,state[3]);
#endif
                    }
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
#if INDEX_NOTIFY
    if(passes)for(int w=0;w<(state[0]+31)/32;w++)head[NOTIFY_BASE+ROW_WORDS+w]=0;
#endif
}
template<int PART=0>
inline void do_commit(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head,device int *wm,device const int *count,device long *tok,
                   device long *rhs,device long *writes,device int *runs,device int *resumes,constant int &lanes,
                   uint gid,device int *scratch=nullptr){
    if(gid||state[5]||state[7])return;
    int run=state[3],base_rhs=state[9],base_write=state[10];
    device int *pending=PART==2?scratch+RULES*513+2:nullptr;
    if(pending)pending[0]=0;
    device const int *rs=rom+SETS+2*state[4];
    for(int idx=0;idx<rs[0];idx++){
        int rid=rom[rs[1]+idx];device const int *rule=rom+RULE+7*rid;
        wm[rid]=run;int ordered[512],n=0;
        int width=input_width(rule),stride=width+5;device const long *bank=tok+token_offset(rom,rid);
        if(PART!=2)for(int lane=0;lane<(SHARED_ARENA?1:PARTS);lane++){
            int bound=SHARED_ARENA?count[2*rid]:count[PARTS*rid+lane];
            if(SHARED_ARENA && count[2*rid+1])bound=count[2*rid+1];if(bound<0){state[5]=bound==-1?3:4;state[6]=rid;return;}
            for(int i=0;i<bound;i++){
                if(n>=512){state[5]=4;state[6]=rid;return;}
                int pos=lane*TOKEN_CAP+i,at=n;
                while(at>0){
                    device const long *a=bank+ordered[at-1]*stride,*b=bank+pos*stride;
                    int order=compare(a,b,rule[4],rom,meta,rid);
                    bool priority=a[width+3]<b[width+3] || (a[width+3]==b[width+3] && a[width+4]>b[width+4]);
                    if(order<0 || (order==0 && !priority))break;
                    ordered[at]=ordered[at-1];at--;
                }
                ordered[at]=pos;n++;
            }
        }
        if(PART==1){
            int unique=0;
            for(int i=0;i<n;i++){
                if(i && compare(bank+ordered[i]*stride,bank+ordered[i-1]*stride,rule[4],rom,meta,rid)==0)continue;
                scratch[rid*513+1+unique++]=ordered[i];
            }
            scratch[rid*513]=unique;continue;
        }
        if(PART==2)n=scratch[rid*513];
        for(int i=0;i<n;i++){
            int pos=PART==2?scratch[rid*513+1+i]:ordered[i];
            device const long *values=bank+pos*stride;
            if(PART!=2 && i && compare(values,bank+ordered[i-1]*stride,rule[4],rom,meta,rid)==0)continue;
#if AUDIT_ROWS
            int proposals[2]={0,0};
            for(int j=i;j<n;j++){
                device const long *candidate=bank+ordered[j]*stride;
                if(compare(values,candidate,rule[4],rom,meta,rid)!=0)break;
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
#if CAPTURE_BOUNDARIES
            for(int k=0;k<3*rule[0];k++)
                meta[BOUNDARY_COMMIT+3*DEPTH*state[9]+k]=meta[BOUNDARY_MATCH+3*DEPTH*(rid*2*TOKEN_CAP+pos)+k];
#endif
            long env[MAXSLOTS],args[WIDTH+2];
#if BIRTH_AUDIT
            device long *born=rhs+TRACE_CAP*(NINPUT+4)+2*state[9];
            born[0]=state[0];
#endif
            device long *log=rhs+(state[9]++)*(NINPUT+4);
#if BLOCK_STUDY
            if(COUNT_WORK){
                int pivot=int(values[width+4]%DEPTH);
                bool certified=values[width+1]!=0 && bake_pivots[rid*DEPTH+pivot]>=0;
                runs[(RUN_CAP+run-1)*6+int(certified)]++;
            }
#endif
#if CO_TRACE
            state[CO_COUNTER+10]=values[width+1]?int(values[width])+1:0;
#endif
#if COMPOUND
            state[76]=0;
#ifdef COM_TAIL_BASE
            state[77]=0;
#endif
            if(values[width]>=0){
                device const int *index=meta+COM_HEAD+2*int(values[width]);
                if(index[0]==run)for(int id=index[1]-1;id>=0;id=claims(meta)[id].next-1){
                    device CompoundClaim &c=claims(meta)[id];
                    if(neural_catalog[4*compound_joins[4*c.join+3]]==rid && c.bank==pos){
                        c.winner=state[9];c.status=6;
#ifdef COM_TAIL_BASE
                        if(compound_tails[c.join]>=0)state[77]=id+1;
#endif
                    }
                }
            }
#endif
#if NEURAL_ACTIVE
            for(int n=0;n<NEURAL_SLOTS;n++){
                device const int *mark=meta+NEURAL_BASE+4*n;
                if(mark[0]==rid && mark[3]==pos){
#if COMPOUND
                    state[76]=n+1;
#endif
#if NEURAL_ORDINAL
                    meta[NEURAL_BASE+4*NEURAL_SLOTS+NEURAL_SLOTS*(run-1)+n]=state[9];
#else
                    meta[NEURAL_BASE+4*NEURAL_SLOTS+NEURAL_SLOTS*(run-1)+n]=1;
#endif
                }
            }
#endif
#if NEURAL_EDGES
            if(values[width+1])meta[EDGE_CONSUMED+state[9]-1]=meta[EDGE_BEFORE+values[width]];
#endif
#if NEURAL_CAPTURE
            meta[NEURAL_BASE+state[9]-1]=values[width+1]?int(values[width+4]%DEPTH)+1:0;
#endif
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
                int kind=op[0],t=op[1],arity=op[3];
                if(kind==3){long v;if(!eval_op(state,meta,t,rom+op[4],arity,env,lits,v)){if(!state[5])state[5]=8;state[6]=rid;return;}env[op[2]]=v;continue;}
                for(int j=0;j<arity;j++)args[j]=operand(rom[op[4]+j],env,lits);
                if(kind==0){env[op[2]]=args[0];continue;}
                if(kind==4){submit_union(state,meta,args[0],args[1],head);if(state[5])return;continue;}
                if(kind==6){state[5]=10;state[6]=rid;return;}
                device const int *schema=table(rom,t);
                if(kind==2)arity--;
                for(int j=0;j<op[3];j++)if(schema[3]&(1<<j))args[j]=root_id(meta,int(args[j]));
                int found=find_key(rom,lits,meta,dyn,head,t,arity,args);
                if(kind==1){
                    if(found<0){args[arity]=long(NSYMBOLS+1+state[0]);found=insert_row(rom,state,meta,dyn,head,t,arity+1,args);}
                    if(found<0)return;publish_anchor(rom,state,meta,t,found,cursor,rid,depth,pending,k,lits,dyn,head);env[op[2]]=field(rom,lits,meta,dyn,found,arity);continue;
                }
                if(kind==5){
                    if(found>=0 && !meta[6*found+3]){meta[6*found+3]=1;touch_row(state,meta,head,found,t,run);state[8]=1;}
                    continue;
                }
                if(kind!=2){state[5]=11;state[6]=rid;return;}
                if(schema[1]){
                    if(found<0)found=insert_row(rom,state,meta,dyn,head,t,arity+1,args);
                    else submit_union(state,meta,field(rom,lits,meta,dyn,found,arity),args[arity],head);
                    if(state[5])return;publish_anchor(rom,state,meta,t,found,cursor,rid,depth,pending,k,lits,dyn,head);
                    continue;
                }
                bool had_old=found>=0;long previous=0;
                if(found>=0){
                    long old=field(rom,lits,meta,dyn,found,arity),v=args[arity];
                    previous=old;v=merge_value(rom,lits,state,meta,dyn,head,t,old,v);
                    if(state[5]){state[6]=rid;return;}
                    if(old==v){publish_anchor(rom,state,meta,t,found,cursor,rid,depth,pending,k,lits,dyn,head);continue;}
                    if(meta[6*found+1]>=0){state[5]=13;state[6]=rid;return;}
                    dyn[found*WIDTH+arity]=v;touch_row(state,meta,head,found,t,run);state[8]=1;
                }else{found=insert_row(rom,state,meta,dyn,head,t,arity+1,args);if(found<0)return;}
                publish_anchor(rom,state,meta,t,found,cursor,rid,depth,pending,k,lits,dyn,head);
                log_write(state,writes,rid,state[9]-base_rhs-1,t,found,args,arity,had_old,previous,
                          field(rom,lits,meta,dyn,found,arity));if(state[5])return;
            }
#if BIRTH_AUDIT
            born[1]=state[0];
#endif
        }
    }
    if(PART){if(PART==2){scratch[RULES*513]=base_rhs;scratch[RULES*513+1]=base_write;}return;}
    state[18]=1;repair(rom,lits,state,meta,dyn,head,writes);state[18]=0;if(state[5])return;
#if REGION_CAPTURE || REGION_SELECT
    region_boundary(rom,lits,meta,dyn,head,state);
#endif
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

#if PHASE_TIMING
kernel void entry_only(device const int *rom,device const long *lits,device int *state,
                   device const int *meta,device const long *dyn,device const int *head,
                   device const int *wm,device int *count,device long *tok,constant int &lanes,
                   uint gid [[thread_position_in_grid]]){ do_search<1,false>(rom,lits,state,meta,dyn,head,wm,count,tok,lanes,gid); }
kernel void spine_only(device const int *rom,device const long *lits,device int *state,
                   device const int *meta,device const long *dyn,device const int *head,
                   device const int *wm,device int *count,device long *tok,constant int &lanes,
                   uint gid [[thread_position_in_grid]]){ do_search<2,false>(rom,lits,state,meta,dyn,head,wm,count,tok,lanes,gid); }
kernel void entry_matches(device const int *rom,device const long *lits,device int *state,
                   device const int *meta,device const long *dyn,device const int *head,
                   device const int *wm,device int *count,device long *tok,constant int &lanes,device int *certs,
                   uint gid [[thread_position_in_grid]]){ do_search<1,true>(rom,lits,state,meta,dyn,head,wm,count,tok,lanes,gid,certs); }
kernel void spine_matches(device const int *rom,device const long *lits,device int *state,
                   device const int *meta,device const long *dyn,device const int *head,
                   device const int *wm,device int *count,device long *tok,constant int &lanes,device int *certs,
                   uint gid [[thread_position_in_grid]]){ do_search<2,true>(rom,lits,state,meta,dyn,head,wm,count,tok,lanes,gid,certs); }
kernel void sort_unique(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head,device int *wm,device const int *count,device long *tok,
                   device long *rhs,device long *writes,device int *runs,device int *resumes,constant int &lanes,device int *scratch,
                   uint gid [[thread_position_in_grid]]){ do_commit<1>(rom,lits,state,meta,dyn,head,wm,count,tok,rhs,writes,runs,resumes,lanes,gid,scratch); }
kernel void apply_rhs(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head,device int *wm,device const int *count,device long *tok,
                   device long *rhs,device long *writes,device int *runs,device int *resumes,constant int &lanes,device int *scratch,
                   uint gid [[thread_position_in_grid]]){ do_commit<2>(rom,lits,state,meta,dyn,head,wm,count,tok,rhs,writes,runs,resumes,lanes,gid,scratch); }
kernel void emit_tokens(device const int *rom,device const long *lits,device int *state,device const int *meta,
                        device const long *dyn,device const int *count,device long *tok,device const int *certs,
                        uint gid [[thread_position_in_grid]]){
    if(state[5]||state[7])return;
    device const int *rs=rom+SETS+2*state[4];int idx=gid/PARTS,lane=gid%PARTS;
    if(idx>=rs[0])return;
    int rid=rom[rs[1]+idx];device const int *rule=rom+RULE+7*rid;
    for(int pos=lane;pos<count[2*rid];pos+=PARTS){
        if(pos>=2*TOKEN_CAP){state[5]=4;return;}
        device const int *rec=certs+(rid*2*TOKEN_CAP+pos)*(DEPTH+3);
        bool routed=rec[0]>=0;device const int *path=rom+(routed?rec[0]:rule[1]);
        long env[MAXSLOTS];
        for(int k=0;k<rule[0];k++){
            device const int *op=path+4*k,*args=rom+op[2];
            if(op[0]<0){
                int j=op[1]-1;
                if(op[3]&(1<<j)){
                    long v=0;
                    if(!eval_op(state,meta,-1-op[0],args,j,env,lits,v)){state[5]=8;return;}
                    env[args[j]]=v;
                }
            }else{
                for(int j=0;j<op[1];j++)if(op[3]&(1<<j))env[args[j]]=field(rom,lits,meta,dyn,rec[3+k],j);
            }
        }
        int width=input_width(rule),seed=rec[1];
        device long *out=tok+token_offset(rom,rid)+pos*(width+5);
        for(int k=0;k<rule[4];k++)out[k]=env[rom[rule[5]+k]];
        out[width]=seed;out[width+1]=0;out[width+3]=0;out[width+4]=0;
        if(routed){
            device const int *h=anchor(meta,seed);
            out[width+1]=h[0];out[width+2]=h[1];out[width+3]=h[2];
            out[width+4]=long((table(rom,path[0])[1]?0:ROW_CAP)+seed)*DEPTH+rec[2];
        }
    }
}
kernel void publish_spine(device const int *rom,device int *state,device int *meta,device const int *scratch,
                          uint gid [[thread_position_in_grid]]){
    if(gid||state[5]||state[7])return;
    device const int *pending=scratch+RULES*513+2;
    for(int i=0;i<pending[0];i++){
        device const int *e=pending+1+5*i;
        publish_anchor(rom,state,meta,e[0],e[1],e[2],e[3],e[4]);
    }
}
kernel void finish_repair(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head,device long *writes,device int *runs,device const int *scratch,
                   uint gid [[thread_position_in_grid]]){
    if(gid||state[5]||state[7])return;
    int run=state[3],base_rhs=scratch[RULES*513],base_write=scratch[RULES*513+1];
    state[18]=1;repair(rom,lits,state,meta,dyn,head,writes);state[18]=0;if(state[5])return;
#if REGION_CAPTURE || REGION_SELECT
    region_boundary(rom,lits,meta,dyn,head,state);
#endif
    if(state[8])state[2]++;
    device int *out=runs+(run-1)*6;out[0]=state[4];out[1]=state[9]-base_rhs;out[2]=state[10]-base_write;
    out[3]=state[8];out[4]=state[0];out[5]=state[2];state[11]=run;
}
#endif
