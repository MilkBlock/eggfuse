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
inline int root_id(device const int *meta,int v){
    device const int *parent=meta+6*ROW_CAP;
    while(parent[v])v=parent[v];
    return v;
}
inline bool unite(device int *state,device int *meta,long a,long b){
    if(a<=0 || b<=0 || a>=UF_SIZE || b>=UF_SIZE){state[5]=14;return false;}
    int x=root_id(meta,int(a)),y=root_id(meta,int(b));
    if(x==y)return false;
    int hi=max(x,y);meta[6*ROW_CAP+hi]=min(x,y);
    meta[6*ROW_CAP+UF_SIZE+hi]=state[3];state[8]=1;state[12]=1;
    return true;
}
inline long field(device const int *rom,device const long *lits,device const int *meta,
                  device const long *dyn,int row,int col){
    long v=rawfield(rom,lits,meta,dyn,row,col);
    return (table(rom,meta[6*row])[3]&(1<<col))?long(root_id(meta,int(v))):v;
}
kernel void inject(device const int *rom,device const int *slots,device int *state,device int *meta,
                   device int *head,device int *order,uint gid [[thread_position_in_grid]]){
    if(gid)return;
    for(int t=0;t<TABLES;t++)head[t]=-1;
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
        }
    }
}
inline long operand(int i,thread long *env,device const long *lits){return i>=0?env[i]:lits[-1-i];}
inline bool prim(int op,long a,long b,thread long &out){
    switch(op){
        case 0:out=0;return a!=b;
        case 1:if(!b || (a==LONG_MIN && b==-1))return false;out=a%b;return true;
        case 2:out=long(ulong(a)*ulong(b));return true;
        case 3:out=long(ulong(a)+ulong(b));return true;
        case 4:out=long(ulong(a)-ulong(b));return true;
        case 5:if(!b || (a==LONG_MIN && b==-1))return false;out=a/b;return true;
        case 6:out=0;return a<b;
        case 7:out=0;return a<=b;
        case 8:out=0;return a>b;
        case 9:out=0;return a>=b;
        case 10:out=a&&b;return true;
        case 11:out=a<b;return true;
        case 12:out=max(a,b);return true;
        case 13:out=min(a,b);return true;
        case 14:out=a||b;return true;
    }
    return false;
}
kernel void next_run(device const int *rom,device int *state,device int *regs,uint gid [[thread_position_in_grid]]){
    if(gid||state[5]||state[7])return;
    while(state[1]<NCTRL){
        device const int *i=rom+CONTROL+4*state[1]++;
        if(i[0]==0){state[4]=i[1];state[3]++;state[8]=0;return;}
        if(i[0]==1)regs[i[1]]=state[2];
        if(i[0]==2 && regs[i[1]]!=state[2])state[1]=i[2];
        if(i[0]==3)regs[i[1]]=i[2];
        if(i[0]==4 && --regs[i[1]] && regs[i[2]]!=state[2])state[1]=i[3];
    }
    state[7]=1;
}
kernel void search(device const int *rom,device const long *lits,device const int *state,
                   device const int *meta,device const long *dyn,device const int *head,
                   device const int *wm,device int *count,device long *tok,constant int &lanes,
                   uint gid [[thread_position_in_grid]]){
    if(state[5]||state[7])return;
    device const int *rs=rom+SETS+2*state[4];int idx=gid/lanes,lane=gid%lanes;
    if(idx>=rs[0])return;
    int r=rom[rs[1]+idx];device const int *rule=rom+RULE+7*r;
    int bank=r*2+lane;count[bank]=0;
    int q=rule[0],pivot=-1,last=wm[r];
    for(int j=0;j<q;j++){int t=rom[rule[1]+4*j];if(t>=0){if(pivot<0)pivot=j;if(head[t]<0)return;}}
    if(pivot<0 && lane)return;
    if(q==0 && rule[6] && last>=0)return;
    long env[MAXSLOTS];int cur[DEPTH],epoch[DEPTH],witness[DEPTH];cur[0]=-2;epoch[0]=0;
    int depth=0,visits=0;
    while(depth>=0){
        if(++visits>SEARCH_CAP){count[bank]=-1;return;}
        if(depth==q){
            if(!rule[6] || epoch[depth]>=last){
                int pos=count[bank]++;
                if(pos>=TOKEN_CAP){count[bank]=-2;return;}
                device long *out=tok+(bank*TOKEN_CAP+pos)*TOKEN_WIDTH;
                for(int j=0;j<rule[4];j++)out[j]=env[rom[rule[5]+j]];
                out[NINPUT]=pivot>=0?witness[pivot]:-1;
            }
            depth--;continue;
        }
        device const int *op=rom+rule[1]+4*depth,*args=rom+op[2];int t=op[0];
        if(cur[depth]==-2)cur[depth]=t<0?0:head[t];
        int row=cur[depth];
        if(row<0){cur[depth]=-2;depth--;continue;}
        bool ok=true;int version=epoch[depth];
        if(t<0){
            cur[depth]=-1;long val=0;
            ok=prim(-1-t,operand(args[0],env,lits),operand(args[1],env,lits),val);
            int lastcol=op[1]-1,key=args[lastcol];
            if(op[3]&(1<<lastcol))env[key]=val;
            else ok &= operand(key,env,lits)==val;
        }else{
            device const int *m=meta+6*row;cur[depth]=m[5];
            if(m[3] || (depth==pivot && row%lanes!=lane))continue;
            for(int j=0;j<op[1];j++){
                long v=field(rom,lits,meta,dyn,row,j);int key=args[j];
                if(op[3]&(1<<j))env[key]=v;
                else if(operand(key,env,lits)!=v){ok=false;break;}
            }
            version=max(version,m[4]);witness[depth]=row;
        }
        if(ok){depth++;epoch[depth]=version;cur[depth]=-2;}
    }
}
inline int find_key(device const int *rom,device const long *lits,device const int *meta,
                    device const long *dyn,device const int *head,int table_id,int arity,thread long *values){
    for(int row=head[table_id];row>=0;row=meta[6*row+5]){
        if(meta[6*row+3]==2)continue;
        bool same=true;
        for(int j=0;j<arity;j++)if(field(rom,lits,meta,dyn,row,j)!=values[j]){same=false;break;}
        if(same)return row;
    }
    return -1;
}
inline int insert_row(device int *state,device int *meta,device long *dyn,device int *head,
                      int t,int n,thread long *values){
    int id=state[0];if(id>=ROW_CAP){state[5]=2;return -1;}
    state[0]++;device int *m=meta+6*id;m[0]=t;m[1]=-1;m[2]=0;m[3]=0;m[4]=state[3];m[5]=head[t];head[t]=id;
    for(int j=0;j<n;j++)dyn[id*WIDTH+j]=values[j];
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
    if(kind==3)return min(old,v);
    if(kind==4)return max(old,v);
    if(kind==5)return max(1L,min(old,v));
    if(kind>=16){
        int ctor=kind-16;long pair[3]={old,v,0};
        int row=find_key(rom,lits,meta,dyn,head,ctor,2,pair);
        if(row<0){pair[2]=NSYMBOLS+1+state[0];row=insert_row(state,meta,dyn,head,ctor,3,pair);}
        return row<0?0:field(rom,lits,meta,dyn,row,2);
    }
    state[5]=12;return old;
}
inline void repair(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head){
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
                bool same=true;for(int j=0;j<last;j++)if(key[j]!=field(rom,lits,meta,dyn,other,j)){same=false;break;}
                if(!same)continue;
                int keep=min(row,other),drop=max(row,other);
                long old=field(rom,lits,meta,dyn,keep,last),v=field(rom,lits,meta,dyn,drop,last);
                if(spec[1])unite(state,meta,old,v);
                else{
                    long next=merge_value(rom,lits,state,meta,dyn,head,t,old,v);
                    if(next!=old){if(meta[6*keep+1]>=0){state[5]=13;return;}dyn[keep*WIDTH+last]=next;meta[6*keep+4]=state[3];}
                }
                if(meta[6*drop+3]==1){meta[6*keep+3]=1;meta[6*keep+4]=state[3];}
                meta[6*drop+3]=2;if(drop==row)break;
            }
        }
    }
}
kernel void commit(device const int *rom,device const long *lits,device int *state,device int *meta,
                   device long *dyn,device int *head,device int *wm,device const int *count,device long *tok,
                   device long *rhs,device long *writes,device int *runs,constant int &lanes,
                   uint gid [[thread_position_in_grid]]){
    if(gid||state[5]||state[7])return;
    int run=state[3],base_rhs=state[9],base_write=state[10];device const int *rs=rom+SETS+2*state[4];
    for(int idx=0;idx<rs[0];idx++){
        int rid=rom[rs[1]+idx];device const int *rule=rom+RULE+7*rid;
        wm[rid]=run;int ordered[2*TOKEN_CAP],n=0;
        device const long *bank=tok+rid*2*TOKEN_CAP*TOKEN_WIDTH;
        for(int lane=0;lane<lanes;lane++){
            int bound=count[2*rid+lane];if(bound<0){state[5]=bound==-1?3:4;state[6]=rid;return;}
            for(int i=0;i<bound;i++){
                int pos=lane*TOKEN_CAP+i,at=n;
                while(at>0 && compare(bank+ordered[at-1]*TOKEN_WIDTH,bank+pos*TOKEN_WIDTH,rule[4])>0){
                    ordered[at]=ordered[at-1];at--;
                }
                ordered[at]=pos;n++;
            }
        }
        for(int i=0;i<n;i++){
            device const long *values=bank+ordered[i]*TOKEN_WIDTH;
            if(i && compare(values,bank+ordered[i-1]*TOKEN_WIDTH,rule[4])==0)continue;
            if(state[9]>=TRACE_CAP){state[5]=5;return;}
            long env[MAXSLOTS],args[WIDTH+2];
            device long *log=rhs+(state[9]++)*(NINPUT+4);
            log[0]=run;log[1]=rid;log[2]=ordered[i]/TOKEN_CAP;log[3]=values[NINPUT];
            for(int j=0;j<rule[4];j++){env[rom[rule[5]+j]]=values[j];log[4+j]=values[j];}
            for(int k=0;k<rule[2];k++){
                device const int *op=rom+rule[3]+5*k;
                for(int j=0;j<op[3];j++)args[j]=operand(rom[op[4]+j],env,lits);
                int kind=op[0],t=op[1],arity=op[3];
                if(kind==0){env[op[2]]=args[0];continue;}
                if(kind==3){long v;if(!prim(t,args[0],args[1],v)){state[5]=8;state[6]=rid;return;}env[op[2]]=v;continue;}
                if(kind==4){unite(state,meta,args[0],args[1]);if(state[5])return;continue;}
                if(kind==6){state[5]=10;state[6]=rid;return;}
                device const int *schema=table(rom,t);
                if(kind==2)arity--;
                for(int j=0;j<op[3];j++)if(schema[3]&(1<<j))args[j]=root_id(meta,int(args[j]));
                int found=find_key(rom,lits,meta,dyn,head,t,arity,args);
                if(kind==1){
                    if(found<0){args[arity]=long(NSYMBOLS+1+state[0]);found=insert_row(state,meta,dyn,head,t,arity+1,args);}
                    if(found<0)return;env[op[2]]=field(rom,lits,meta,dyn,found,arity);continue;
                }
                if(kind==5){
                    if(found>=0 && !meta[6*found+3]){meta[6*found+3]=1;meta[6*found+4]=run;state[8]=1;}
                    continue;
                }
                if(kind!=2){state[5]=11;state[6]=rid;return;}
                if(schema[1]){
                    if(found<0)insert_row(state,meta,dyn,head,t,arity+1,args);
                    else unite(state,meta,field(rom,lits,meta,dyn,found,arity),args[arity]);
                    if(state[5])return;
                    continue;
                }
                if(found>=0){
                    long old=field(rom,lits,meta,dyn,found,arity),v=args[arity];
                    v=merge_value(rom,lits,state,meta,dyn,head,t,old,v);
                    if(state[5]){state[6]=rid;return;}
                    if(old==v)continue;
                    if(meta[6*found+1]>=0){state[5]=13;state[6]=rid;return;}
                    dyn[found*WIDTH+arity]=v;meta[6*found+4]=run;state[8]=1;
                }else{found=insert_row(state,meta,dyn,head,t,arity+1,args);if(found<0)return;}
                if(state[10]>=TRACE_CAP){state[5]=5;return;}
                device long *w=writes+(state[10]++)*(WIDTH+5);w[0]=run;w[1]=rid;w[2]=t;w[3]=found;w[WIDTH+4]=state[9]-base_rhs-1;
                for(int j=0;j<=arity;j++)w[4+j]=field(rom,lits,meta,dyn,found,j);
            }
        }
    }
    repair(rom,lits,state,meta,dyn,head);if(state[5])return;
    if(state[8])state[2]++;
    device int *out=runs+(run-1)*6;out[0]=state[4];out[1]=state[9]-base_rhs;out[2]=state[10]-base_write;
    out[3]=state[8];out[4]=state[0];out[5]=state[2];state[11]=run;
}
kernel void export_rows(device const int *rom,device const long *lits,device const int *state,
                        device const int *meta,device const long *dyn,device long *out,uint id [[thread_position_in_grid]]){
    if(id>=uint(state[0]))return;
    for(int j=0;j<table(rom,meta[6*id])[0];j++)out[id*WIDTH+j]=field(rom,lits,meta,dyn,id,j);
}
