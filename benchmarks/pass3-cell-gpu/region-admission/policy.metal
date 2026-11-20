// A region covers 32 consecutive physical row addresses. Membership is changed
// only after ordered repair/publication at the end of a source Run.
constant int REG_WORDS=ROW_CAP/32;
constant int REG_SLOT=REG_BASE;
constant int REG_SELECTED=REG_SLOT+REG_WORDS;
constant int REG_CHANGES=REG_SELECTED+REG_WORDS;
constant int REG_WORD=REG_CHANGES+REG_WORDS;
constant int REG_GENERATION=REG_WORD+REG_BUDGET;
constant int REG_PAYLOAD=REG_GENERATION+REG_BUDGET;
constant int REG_HEAD=TABLES*((USE_INDEX?257:1)+((TILES>1||LEARN_OWNER)?PARTS:0)+(HOT_FILTER>0)+((HOT_FILTER==2||HOT_FILTER==3)?PARTS:0));

inline void region_edge(device uint *bits,device int *meta,int slot,int root,uint mask){
    // Each reusable slot has its own generation; an evicted bitmap cannot
    // supply a wake for the next physical region occupying the same slot.
    device uint *entry=bits+2*REG_WORDS+2*(root*REG_BUDGET+slot);
    uint generation=uint(meta[REG_GENERATION+slot]);
    if(entry[0]!=generation){entry[0]=generation;entry[1]=mask;}else entry[1]|=mask;
}
inline void region_add(device const int *rom,device const long *lits,device int *meta,
                       device const long *dyn,device int *head,device int *state,int row,int t){
    device uint *bits=(device uint *)(head+REG_HEAD);
    int w=row/32,slot=meta[REG_SLOT+w]-1;uint bit=1u<<(row%32);
    if(slot<0 || repair_shapes[t]<0){bits[w]|=bit;return;}
    device const int *spec=table(rom,t);
    for(int c=0;c<spec[0];c++)if(spec[3]&(1<<c)){
        region_edge(bits,meta,slot,root_id(meta,int(rawfield(rom,lits,meta,dyn,row,c))),bit);
        study_add(state,73);
    }
}
inline void region_notify(device int *meta,device int *head,device int *state,int hi,int lo){
    device uint *bits=(device uint *)(head+REG_HEAD);
    for(int slot=0;slot<REG_BUDGET;slot++){
        int w=meta[REG_WORD+slot]-1;
        if(w<0)continue;
        if(COUNT_WORK)state[74]++;
        device uint *entry=bits+2*REG_WORDS+2*(hi*REG_BUDGET+slot);
        if(entry[0]!=uint(meta[REG_GENERATION+slot]))continue;
        uint affected=entry[1];
        bits[REG_WORDS+w]|=affected;region_edge(bits,meta,slot,lo,affected);
    }
}

inline void region_boundary(device const int *rom,device const long *lits,device int *meta,
                            device const long *dyn,device int *head,device int *state){
    if(state[3]%REG_WINDOW!=0)return;
    int words=(state[0]+31)/32, passes=state[REG_COUNTER];
    state[REG_COUNTER]=0;
    int best[REG_BUDGET];float scores[REG_BUDGET];int n=0;
    for(int w=0;w<words;w++){
        int live=0,ports=0,newrows=0;
        int begin=w*32,end=min(begin+32,state[0]);
        for(int row=begin;row<end;row++){
            if(meta[6*row+3]==2 || repair_shapes[meta[6*row]]<0)continue;
            live++;
            ports+=int(popcount(uint(table(rom,meta[6*row])[3])));
            int birth=abs(meta[BIRTH_RUN+row]);
            newrows+=int(birth>state[3]-REG_WINDOW);
        }
        int dirty=meta[REG_CHANGES+w];meta[REG_CHANGES+w]=0;
        int x[6]={live,ports,newrows,min(dirty,1024),min(passes,128),live*min(passes,128)};
#if REGION_CAPTURE
        // Features recorded for the *following* window. Its labels accumulate
        // when a real repair inspects a row, including the final partial window.
        device int *record=meta+REG_PAYLOAD+8*((state[3]/REG_WINDOW)*REG_WORDS+w);
        for(int j=0;j<6;j++)record[j]=x[j];
#endif
#if REGION_SELECT
        meta[REG_SELECTED+w]=0;
        if(!live)continue;
#if REGION_ORACLE
        uint selected=region_oracle[(state[3]/REG_WINDOW)*(REG_WORDS/32)+w/32];
        float score=(selected&(1u<<(w%32)))?1.f:0.f;
#else
        float score=region_bias;
        for(int j=0;j<6;j++)score+=region_weights[j]*float(x[j]);
        // A new admission reads its actual live rows. Charge this in the
        // policy's work estimate as well as in execution.
        if(!meta[REG_SLOT+w])score-=float(live)*region_build_price;
#endif
        if(score<=0 || (n==REG_BUDGET && score<=scores[n-1]))continue;
        int pos=min(n,REG_BUDGET-1);
        while(pos>0 && score>scores[pos-1]){
            if(pos<REG_BUDGET){scores[pos]=scores[pos-1];best[pos]=best[pos-1];}
            pos--;
        }
        scores[pos]=score;best[pos]=w;n=min(n+1,REG_BUDGET);
#endif
    }
#if REGION_SELECT
    device uint *bits=(device uint *)(head+REG_HEAD);
    for(int i=0;i<n;i++){
        int word=best[i];meta[REG_SELECTED+word]=1;
        if(COUNT_WORK) ((device uint *)(meta+REG_PAYLOAD))[(state[3]/REG_WINDOW)*(REG_WORDS/32)+word/32]|=1u<<(word%32);
    }
    for(int slot=0;slot<REG_BUDGET;slot++){
        int old=meta[REG_WORD+slot]-1;
        if(old<0 || meta[REG_SELECTED+old])continue;
        meta[REG_SLOT+old]=0;meta[REG_WORD+slot]=0;
        bits[old]=~0u;study_add(state,REG_COUNTER+2);
    }
    int free=0;
    for(int i=0;i<n;i++){
        int w=best[i];if(meta[REG_SLOT+w])continue;
        while(free<REG_BUDGET && meta[REG_WORD+free])free++;
        if(free==REG_BUDGET){state[5]=23;return;}
        meta[REG_WORD+free]=w+1;meta[REG_SLOT+w]=free+1;meta[REG_GENERATION+free]++;
        bits[w]=0;study_add(state,REG_COUNTER+1);
        for(int row=32*w;row<min(32*w+32,state[0]);row++){
            if(meta[6*row+3]==2)continue;
            region_add(rom,lits,meta,dyn,head,state,row,meta[6*row]);
            study_add(state,REG_COUNTER+3);
        }
    }
    if(COUNT_WORK){
        state[REG_COUNTER+4]=max(state[REG_COUNTER+4],n);
        state[REG_COUNTER+5]+=n;state[REG_COUNTER+6]++;
    }
#endif
}
