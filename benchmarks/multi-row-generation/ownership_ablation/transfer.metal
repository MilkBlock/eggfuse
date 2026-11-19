#include <metal_stdlib>
using namespace metal;

// Both proposed pairs have already been scored on device. Each graph applies
// source effect order. A row that lost its claim can receive one newly ranked pair.
kernel void commit(device float *source, device int *headers, device float *residual,
                   device int *boundary, device int *targets, device const int *actions,
                   device int *log, device const int *plan, constant int& round,
                   constant int& mode, uint graph [[thread_position_in_grid]]) {
    for(int row=0;row<2;row++){
        int entry=((graph*2+round)*2+row)*3;
        int l=actions[(graph*2+row)*2], r=actions[(graph*2+row)*2+1];
        log[entry]=l;log[entry+1]=r;
        device int *target=targets+(graph*2+row)*3;
        if(round && log[(graph*4+row)*3+2]!=2) continue;
        if(target[0] || l<0 || r<0 || l>=8 || r>=8 || l==r){log[entry+2]=3;continue;}
        device int *lh=headers+(graph*8+l)*5, *rh=headers+(graph*8+r)*5;
        if(mode!=2 && (lh[2]>=0 || rh[2]>=0)){log[entry+2]=2;continue;}
        device float *left=source+(graph*8+l)*56, *right=source+(graph*8+r)*56;
        bool valid=left[33]>left[32] && right[33]>right[32] && left[50]==right[50] && left[54]==right[54];
        for(int j=42;j<50;j++) valid &= left[j]==right[j];
        if(!valid){log[entry+2]=3;continue;}
        // The shared B witness licenses the two shared boundary ports.
        for(int j=0;j<8;j++){
            int side=plan[2*j], col=plan[2*j+1];
            boundary[(graph*2+row)*8+j]=int((side?right:left)[50+col]);
        }
        target[0]=1;target[1]=l;target[2]=r;
        for(int side=0;side<2;side++){
            device float *record=side?right:left;
            device float *dst=residual+((graph*2+row)*2+side)*51;
            for(int j=0;j<50;j++) dst[j]=record[j];
            dst[50]=record[55];
            device int *h=side?rh:lh;
            h[1]=1;h[2]=row;h[3]=plan[26+side];h[4]=target[0];
            if(mode==1){ // reuse the old physical slot at generation 2
                h[0]=2;
                for(int j=0;j<56;j++) record[j]=-float(1+56*(side?r:l)+j);
            }
        }
        log[entry+2]=1;
    }
}

// refs: (original physical source slot, expected generation). Never read a
// retired source frame to service a forwarded cursor.
kernel void resolve(device const float *source, device const int *headers,
                    device const float *residual, device const int *boundary,
                    device const int *targets, device const int *refs, device const int *plan,
                    device float *out, device int *status, constant int& width,
                    constant int& blind, uint gid [[thread_position_in_grid]]) {
    int graph=gid/width, slot=refs[2*gid], gen=refs[2*gid+1];
    int code=0,side=0,dest=0;
    if(slot>=0 && slot<8){
        device const int *h=headers+(graph*8+slot)*5;
        if(gen==h[0] || blind) code=1;
        else if(gen==h[1] && h[2]>=0 && h[2]<2){
            dest=h[2]; side=h[3]==plan[26]?0:1;
            device const int *t=targets+(graph*2+dest)*3;
            if(t[0]==h[4] && t[0]>0 && h[3]==plan[26+side] && t[side+1]==slot) code=2;
        }
    }
    status[gid]=code;
    for(int j=0;j<56;j++){
        float v=-1;
        if(code==1) v=source[(graph*8+slot)*56+j];
        if(code==2){
            if(j>=50 && j<55) v=boundary[(graph*2+dest)*8+plan[16+side*5+j-50]];
            else v=residual[((graph*2+dest)*2+side)*51+(j==55?50:j)];
        }
        out[gid*56+j]=v;
    }
}
