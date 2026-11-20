// Included only by the co-repair experiment. All physical rows retain their
// source addresses; one owner may share a subscription with up to two readers.
constant int CO_CHILD1 = CO_BASE + ROW_CAP;
constant int CO_CHILD2 = CO_CHILD1 + ROW_CAP;
constant int CO_HAS_CHILD = CO_CHILD2 + ROW_CAP;
constant int CO_EPOCH = CO_HAS_CHILD + ROW_WORDS;
constant int CO_PORTS = CO_EPOCH + ROW_CAP;
constant int CO_DICT_ID = CO_PORTS + ROW_CAP;
constant int CO_JOIN = CO_DICT_ID + ROW_CAP;
constant int CO_DICT = CO_JOIN + ROW_CAP;

inline void co_count(device int *state, int n, int count=1) {
    if(COUNT_WORK) state[CO_COUNTER+n]+=count;
}

inline void co_port(device int *meta, int group, int v, int member, int col) {
    device int *dict=meta+CO_DICT+group*CO_DICT_WORDS;
    int k=0;
    for(; k<dict[0]; k++) if(dict[1+4*k]==v) break;
    // Three scalar constructors have at most three times WIDTH distinct ports.
    if(k==dict[0]) {dict[0]++;dict[1+4*k]=v;}
    dict[2+4*k+member]|=1<<col;
}

inline void co_install_ports(device const int *rom,device const int *source,device int *meta,
                             device const long *dyn,int row,int group,int member) {
    // Groups admit only dynamic scalar constructors with immutable birth values.
    int t=meta[6*row];device const int *spec=table(rom,t);
    for(int c=0;c<spec[0];c++)if(spec[3]&(1<<c)){
        int v=root_id(meta,int(rawfield(rom,nullptr,source,dyn,row,c)));
        co_port(meta,group,v,member,c);
    }
}

inline int co_owner(device const int *rom,device const long *lits,device int *meta,
                    device const long *dyn,device int *state,int row,int t) {
    device const int *spec=table(rom,t);
    int owner=row, chosen=-1, priority=CO_LIBRARY;
#if CO_NESTED
    bool extending=false;
#endif
    if(meta[6*row+1]<0){
        for(int col=0;col<spec[0]-1;col++) if(spec[3]&(1<<col)){
            int v=root_id(meta,int(rawfield(rom,lits,meta,dyn,row,col)));
            int donor=v-NSYMBOLS-1;
            if(donor<0 || donor>=row || meta[6*donor+3] || meta[6*donor+1]>=0)continue;
            int dt=meta[6*donor];
            if(repair_shapes[dt]<0 || dyn[donor*WIDTH+table(rom,dt)[0]-1]!=v)continue;
#if CO_TRACE
            // Negative means this very donor row was the actual Spine pivot.
            bool resumed=!state[18] && state[CO_COUNTER+10]==donor+1;
            meta[CO_EDGES+row*WIDTH+col]=(resumed?-1:1)*(donor+1);
#endif
#if CO_MODE>=2
            if(CO_MEMBERS<2 || meta[CO_BASE+donor] || meta[CO_CHILD2+donor] ||
               (CO_MEMBERS==2 && meta[CO_CHILD1+donor]))continue;
#if CO_NESTED
            bool second=meta[CO_CHILD1+donor]!=0;
            // A second child must never displace the original one-reader
            // choice or consume a future producer for a baseline pair.
            if(second && ((!extending && chosen>=0) || co_producer_table[t]))continue;
            int end=(!second && extending)?CO_LIBRARY:priority;
#else
            int end=priority;
#endif
            for(int i=0;i<end;i++){
                if(co_library[3*i]==dt && co_library[3*i+1]==t && co_library[3*i+2]==col){
                    chosen=donor;priority=i;
#if CO_NESTED
                    extending=second;
#endif
                    break;
                }
            }
#endif
        }
    }
#if CO_MODE>=2
    if(chosen>=0){
        owner=chosen;meta[CO_BASE+row]=owner+1;
#if CO_MODE==3
        meta[CO_JOIN+row]=state[3];meta[CO_JOIN+owner]=state[3];
#endif
        bool first=meta[CO_CHILD1+owner]==0;
        meta[(first?CO_CHILD1:CO_CHILD2)+owner]=row+1;
        ((device uint *)(meta+CO_HAS_CHILD))[owner/32]|=1u<<(owner%32);
        co_count(state,0,int(first));co_count(state,1);
#if CO_MODE==3
        int group=meta[CO_DICT_ID+owner]-1;
        if(group<0){
            group=state[CO_COUNTER+11]++;
            meta[CO_DICT_ID+owner]=group+1;
            co_install_ports(rom,meta,meta,dyn,owner,group,0);
        }
        co_install_ports(rom,meta,meta,dyn,row,group,first?1:2);
#endif
    }
#endif
#if CO_TRACE
    for(int c=0;c<spec[0];c++)if(spec[3]&(1<<c))
        meta[CO_FIELDS+row*WIDTH+c]=int(rawfield(rom,lits,meta,dyn,row,c));
#endif
#if CO_SOLO
    if(owner==row && meta[6*row+1]<0 && co_producer_table[t]){
        int group=state[CO_COUNTER+11]++;
        meta[CO_DICT_ID+row]=group+1;
        ((device uint *)(meta+CO_HAS_CHILD))[row/32]|=1u<<(row%32);
        meta[CO_JOIN+row]=state[3];
        co_install_ports(rom,meta,meta,dyn,row,group,0);
    }
#endif
    return CO_MODE==4?row:owner;
}

inline void co_mark(device int *meta,device uint *dirty,device int *state,int row,int fields) {
    if(!fields)return;
    if(meta[CO_EPOCH+row]!=state[3]){
        meta[CO_EPOCH+row]=state[3];meta[CO_PORTS+row]=0;
    }
    meta[CO_PORTS+row]|=fields;
    dirty[row/32]|=1u<<(row%32);
}

inline uint co_notify(device int *meta,device uint *dirty,device int *state,int word,
                      uint affected,int hi,int lo){
    co_count(state,2,int(popcount(affected)));
#if CO_TRACE
    for(uint bits=affected;bits;bits&=bits-1){
        int row=word*32+ctz(bits);
        if(meta[6*row+3]==2)continue;
        int mask=0;
        for(int c=0;c<WIDTH;c++){
            int v=meta[CO_FIELDS+row*WIDTH+c];
            if(v && root_id(meta,v)==hi)mask|=1<<c;
        }
        if(!mask)continue;
        int at=state[CO_COUNTER+12]++;
        if(at>=TRACE_CAP){state[5]=21;return affected;}
        device int *record=meta+CO_EVENTS+3*at;
        record[0]=state[14]-1;record[1]=row;record[2]=mask;
    }
#endif
#if CO_MODE==2 || CO_MODE==3
    uint groups=affected & ((device uint *)(meta+CO_HAS_CHILD))[word];
    for(uint bits=groups;bits;bits&=bits-1){
        int owner=32*word+ctz(bits),c1=meta[CO_CHILD1+owner]-1,c2=meta[CO_CHILD2+owner]-1;
        co_count(state,3);
#if CO_MODE==2
        dirty[c1/32]|=1u<<(c1%32);
        if(c2>=0)dirty[c2/32]|=1u<<(c2%32);
        co_count(state,4,1+int(c2>=0));
#else
        device int *dict=meta+CO_DICT+(meta[CO_DICT_ID+owner]-1)*CO_DICT_WORDS;
        int from=-1,to=-1;
        for(int k=0;k<dict[0];k++){
            if(dict[1+4*k]==hi)from=k;
            if(dict[1+4*k]==lo)to=k;
        }
        if(from<0){state[5]=22;return affected;}
        device int *record=dict+1+4*from;
        co_mark(meta,dirty,state,owner,record[1]);
        if(c1>=0)co_mark(meta,dirty,state,c1,record[2]);
        if(c2>=0)co_mark(meta,dirty,state,c2,record[3]);
        if(to<0)record[0]=lo;
        else{
            for(int j=1;j<=3;j++)dict[1+4*to+j]|=record[j];
            int last=--dict[0];
            if(from!=last)for(int j=0;j<4;j++)record[j]=dict[1+4*last+j];
            for(int j=0;j<4;j++)dict[1+4*last+j]=0;
        }
        co_count(state,5);
#endif
    }
#if CO_MODE==3
    return affected & ~groups;
#endif
#endif
    return affected;
}
