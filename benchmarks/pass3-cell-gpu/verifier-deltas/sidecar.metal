#include <metal_stdlib>
using namespace metal;
// Four header words and one per RHS slot are returned for each static child slot.
kernel void validate(device const int *catalog,device const int *ports,device const int *schedule,
                     device const uint *done,device int *result,constant int &width,uint id [[thread_position_in_grid]]){
    int ncat=11+width,port_width=8+width,res_width=4+width;
    device const int *c=catalog+id*ncat;device int *out=result+id*res_width;out[0]=0;
    if(c[0]<0 || done[id] || schedule[c[3]]<0)return;
    device const int *p=ports+c[0]*port_width;
    // Source fact/version, the publisher's actual current output, table, visibility and watermark.
    if(!p[0] || p[1]<1 || p[2]!=c[1] || p[3]!=c[2] || p[4]!=c[5] || p[5]<schedule[c[3]] || p[6])return;
    if(c[6]!=c[1] || c[7]!=c[2] || c[8]!=c[3] || c[9]!=c[4])return;
    out[1]=p[0];out[2]=p[1];out[3]=c[10];
    for(int j=0;j<c[10];j++){
        int col=c[11+j];if(col<0 || col>=p[7])return;
        int value=p[8+col];if(value<=0)return;out[4+j]=value;
    }
    out[0]=1;
}
