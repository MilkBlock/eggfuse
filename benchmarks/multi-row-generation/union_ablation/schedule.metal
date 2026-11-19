#include <metal_stdlib>
using namespace metal;

// A class is represented by its smallest vertex. One thread owns the full
// bounded fixture graph; graphs run in parallel. No host-visible intermediate.
inline bool join(device int *cls,int size,int a,int b) {
    int x=cls[a], y=cls[b];
    if(x==y) return false;
    int old=max(x,y), replacement=min(x,y);
    for(int i=0;i<size;i++) if(cls[i]==old) cls[i]=replacement;
    return true;
}

// Bookkeeping: counters [0..11], queue size 12, three pairs [13..18],
// negative cache tags [19..22] (zero=empty), current epoch counter 3.
kernel void advance(device int *classes, device int *book,
                    device const int *event, device const int *requests,
                    device const int *plan, device int *snapshot,
                    constant int& flags, constant int& event_count, uint gid [[thread_position_in_grid]]) {
    int size=plan[0];
    device int *cls=classes+gid*size, *b=book+gid*23;
    for(int i=0;i<event_count;i++) {
        device const int *e=event+2*(gid*event_count+i);
        if(e[0]<0) continue;
        int count=b[12]++;
        b[13+count*2]=e[0]; b[14+count*2]=e[1];
        b[0]++; b[9]=max(b[9],count+1);
    }
    if((flags&1) && b[12]) {
        b[1]++;
        bool changed=false;
        for(int j=0;j<b[12];j++) {
            bool merged=join(cls,size,b[13+2*j],b[14+2*j]);
            b[2]+=int(merged); changed|=merged;
        }
        b[12]=0;
        if(changed) {
            b[3]++;
            if(!(flags&4)) {
                bool again=true;
                while(again) {
                    again=false; b[4]++;
                    int at=8;
                    for(int rule=0;rule<plan[1];rule++) {
                        int x=plan[at++],y=plan[at++],arity=plan[at++];
                        bool proved=cls[x]!=cls[y]; b[5]++;
                        for(int j=0;j<arity;j++,at+=2) proved &= cls[plan[at]]==cls[plan[at+1]];
                        if(proved) { join(cls,size,x,y); b[6]++; again=true; }
                    }
                }
            }
        }
    }
    if(!(flags&2)) return;
    device int *out=snapshot+gid*10;
    for(int p=0;p<6;p++) out[p]=cls[plan[2+p]];
    for(int j=0;j<4;j++) {
        int tag=b[19+j], current=1+b[3];
        if(tag && (tag==current || (flags&8))) {
            b[10]++; out[6+j]=0; continue;
        }
        int offset=gid*8+j*2;
        bool found=cls[requests[offset]]==cls[requests[offset+1]];
        if(tag) { b[7]++; if(found) b[8]++; }
        out[6+j]=int(found); b[19+j]=found?0:current; b[11]++;
    }
}
