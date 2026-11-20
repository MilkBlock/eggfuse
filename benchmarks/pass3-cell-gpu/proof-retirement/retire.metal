// Only unresolved child certificates can be retired. Old published effects stay in source order.
inline void retire_pending(device int *state,device int *meta,int live){
    int run=state[3];
    bool failed_parent=false;
    for(int lane=0;lane<2;lane++){
        device CompoundClaim &c=claims(meta)[(run-1)*2+lane];
        if(c.status!=1)continue;
        if(c.parent<0 || c.parent>=2 || meta[NEURAL_BASE+4*c.parent]<0){
            c.status=7;c.verified=run;failed_parent=true;
        }
    }
    if(RETIRE_BATCH && failed_parent){
        for(int lane=0;lane<2;lane++){
            device CompoundClaim &c=claims(meta)[(run-1)*2+lane];
            if(c.status==1){c.status=8;c.verified=run;}
        }
    }
    // Classify invalid versions first. A second failed proof is never charged as collateral.
    for(int i=0;i<live;i++){
        int id=meta[COM_QUEUE+i];device CompoundClaim &c=claims(meta)[id];
        if(c.status!=2)continue;
        int hidden=meta[6*c.row+3],current=anchor(meta,c.row)[4];
        if(hidden || current!=c.ticket){
            c.status=3;c.verified=run;
            c.bank=hidden?-hidden:current;
        }
    }
    if(RETIRE_BATCH){
        for(int i=0;i<live;i++){
            int id=meta[COM_QUEUE+i];device CompoundClaim &c=claims(meta)[id];
            if(c.status!=3 || c.verified!=run)continue;
            device CompoundClaim &sibling=claims(meta)[id^1];
            if(sibling.status==2){sibling.status=8;sibling.verified=run;}
        }
    }
}
