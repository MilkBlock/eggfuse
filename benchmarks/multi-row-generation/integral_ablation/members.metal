#include <metal_stdlib>
using namespace metal;

// One graph is owned by one lane. Each of its four Cells has four logical
// member ports. A port names a physical record in the graph's 16-record arena.
// record = allocation serial, Cell, op, birth Run, public, parent record serial,
// original physical Pair slot, compared-at-B, compared-at-C, owner, handle,
// request tag, payload, producer tag. Dead records retain no readable fields.
constant int WIDTH=14;
inline int due(int op){return op==0?0:(op<3?1:2);}

// A page contributes four records per graph. Earlier pages stay at the
// same device address when a later Run allocates another page.
inline device int *member(int slot, uint graph,device int *p0,device int *p1,device int *p2,device int *p3){
    device int *page=slot<4?p0:(slot<8?p1:(slot<12?p2:p3));
    return page+(graph*4+slot%4)*WIDTH;
}
#define MEMBER(s) member((s),graph,p0,p1,p2,p3)

kernel void saturate(device const int *input,device const int *observed,
                     device const int *admission,device int *ports,device int *p0,
                     device int *p1,device int *p2,device int *p3,device int *ledger,
                     device int *visible,constant int& stage,constant int& mode,
                     constant int& capacity,uint graph [[thread_position_in_grid]]){
    device int *h=ports+graph*16,*log=ledger+graph*24;
    device int *pub=visible+graph*16*WIDTH;
    // counters: live, high water, serial, rounds; per-op allocs, retired,
    // released precomputed, evaluated early, and total primary publications.
    for(int q=0;q<4;q++){
        int eq=observed[graph*10+6+q];
        bool invalid_parent=false;
        for(int op=0;op<4;op++){
            int slot=h[q*4+op];
            if(slot<0)continue;
            device int *r=MEMBER(slot);
            if(due(op)<stage)continue;
            bool expired=invalid_parent || ((op==1 || op==3) && r[op==1?7:8]!=eq);
            if(mode!=3 && expired){
                for(int i=0;i<WIDTH;i++)r[i]=-1;
                h[q*4+op]=-1;log[0]--;log[8+op]++;invalid_parent=true;
            }
        }
    }
    // A valid precomputed member becomes visible at its original Run. Descendants
    // check their parent serial on release, including when both are due in B.
    for(int q=0;q<4;q++)for(int op=0;op<4;op++){
        int slot=h[4*q+op];
        if(slot<0 || due(op)!=stage)continue;
        device int *r=MEMBER(slot);
        if(op>0){
            int prev=h[4*q+op-1]; if(prev<0 || MEMBER(prev)[0]!=r[5] || !MEMBER(prev)[4]){log[22]++;continue;}
        }
        r[4]=1;log[12+op]++;log[20]++;
    }
    for(int sweep=0;sweep<6;sweep++){
        int primary=0,total=0;log[3]++;
        for(int q=0;q<4;q++){
            device const int *a=input+(graph*4+q)*7;
            int eq=observed[graph*10+6+q];
            // Reverse scan realizes synchronous dependencies without a second arena.
            for(int op=3;op>=0;op--){
                int target=due(op);if(target<stage || h[q*4+op]>=0 || a[0]<0)continue;
                if(target>stage && (mode==0 || !admission[graph*4+q] || (mode==5 && !eq)))continue;
                int pred=op>0?h[q*4+op-1]:-1;
                if(op>0 && pred<0)continue;
                device int *parent=MEMBER(max(pred,0));
                if(op>0 && target==stage && !parent[4])continue;
                int slot=0;while(slot<capacity && MEMBER(slot)[0]>=0)slot++;
                if(slot==capacity){log[22]++;continue;}
                device int *r=MEMBER(slot);
                r[0]=++log[2];r[1]=q;r[2]=op;r[3]=stage;r[4]=(target==stage || mode==4);
                r[5]=op==0?-1:parent[0];r[6]=op==0?a[0]:parent[6];
                r[7]=op==0?-1:(op==1?eq:parent[7]);r[8]=op==3?eq:-1;
                for(int col=0;col<5;col++) r[9+col]=op==0?a[1+col]:parent[9+col];
                if(op==2)r[11]=a[6]; // the stage-B RHS replaces raw id with Request tag
                h[4*q+op]=slot;log[0]++;log[1]=max(log[1],log[0]);
                log[4+op]++;total++;if(target==stage){primary++;log[20]++;}else log[16+op]++;
            }
        }
        if((mode==1?primary:total)==0)break;
        if(sweep==5)log[22]++;
    }
    for(int j=0;j<16;j++){
        int slot=h[j];
        for(int k=0;k<WIDTH;k++)pub[j*WIDTH+k]=(slot>=0 && MEMBER(slot)[4])?MEMBER(slot)[k]:-1;
    }
}
