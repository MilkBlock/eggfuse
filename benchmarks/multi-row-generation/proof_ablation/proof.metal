#include <metal_stdlib>
using namespace metal;

// Each graph has a fixed-capacity transport segment. Active packets are packed
// back-to-back; the verifier is bounded by the supplied slice for each claim.
// cfg: template, epoch, vertex count, macro count, max payload, implication count,
// six public vertices, two local port ordinals.
kernel void issue(device const int *proposals, device const int *request, device const int *ctx,
                  device const int *routes, device const int *macros, device const int *code,
                  device const int *cfg, device int *wire, device int *ranges,
                  constant int &macro, uint graph [[thread_position_in_grid]]) {
    int stride=8*(6+(macro?1:cfg[4])),at=0;
    device int *out=wire+graph*stride;
    for(int j=0;j<8;j++){
        int id=graph*8+j;
        device const int *claim=proposals+id*8;
        ranges[2*id]=at;ranges[2*id+1]=0;
        if(!claim[0])continue;
        int r=claim[2],m=-1;
        if(r>=0 && r<4){
            device const int *q=request+(graph*4+r)*7;
            m=routes[((ctx[graph*2]*10+ctx[graph*2+1])*6+q[5])*6+q[6]];
        }
        int words=m<0?0:(macro?1:macros[6*m+5]);
        out[at]=cfg[0];out[at+1]=cfg[1];out[at+2]=graph;out[at+3]=claim[1];
        out[at+4]=r;out[at+5]=words;
        for(int k=0;k<words;k++)out[at+6+k]=macro?m:code[macros[6*m+4]+k];
        ranges[2*id+1]=6+words;at+=6+words;
    }
}

inline bool replay(device const int *proof,int len,device const int *cfg,device const int *rules,
                   int mask,int edge,int want_a,int want_b,thread int &work){
    int left[32],right[32],n=0;
    for(int i=0;i<len;i++){
        int w=proof[i],op=w/256,v=w%256;
        work++;
        if(w<0)return false;
        if(op<=2){
            if(n==32)return false;
            if(op==0){if(v>=cfg[2])return false;left[n]=right[n]=v;}
            if(op==1){
                if(v>=2 || !(mask&(1<<v)))return false;
                left[n]=cfg[6+3*v+cfg[12]];right[n]=cfg[6+3*v+cfg[13]];
            }
            if(op==2){
                if(v>=9 || edge!=v+1)return false;
                left[n]=cfg[6+v/3];right[n]=cfg[9+v%3];
            }
            n++;continue;
        }
        if(op==3 && !v && n>0){int x=left[n-1];left[n-1]=right[n-1];right[n-1]=x;continue;}
        if(op==4 && !v && n>=2){
            if(right[n-2]!=left[n-1])return false;
            right[n-2]=right[n-1];n--;continue;
        }
        if(op==5 && v<cfg[5]){
            device const int *r=rules+rules[v];int arity=r[2];
            if(n<arity || n-arity>=32)return false;
            for(int k=0;k<arity;k++){
                if(left[n-arity+k]!=r[3+k*2] || right[n-arity+k]!=r[4+k*2])return false;
            }
            n-=arity;left[n]=r[0];right[n++]=r[1];continue;
        }
        return false;
    }
    return n==1 && left[0]==want_a && right[0]==want_b;
}

kernel void verify(device const int *a,device const int *b,device const int *parents,
                   device const int *claims,device const int *request,device const int *ctx,
                   device const int *cfg,device const int *rules,device const int *macros,
                   device const int *wire,device const int *ranges,device int *verdict,
                   constant int &macro,uint id [[thread_position_in_grid]]){
    int graph=id/8,stride=8*(6+(macro?1:cfg[4])),off=ranges[id*2],size=ranges[id*2+1];
    device int *result=verdict+id*2;
    result[0]=0;result[1]=0;
    device const int *claim=claims+id*8;
    if(!claim[0] || off<0 || off>stride || size<7 || size>stride-off)return;
    device const int *msg=wire+graph*stride+off;
    if(msg[0]!=cfg[0] || msg[1]!=cfg[1] || msg[2]!=graph || msg[5]!=size-6)return;
    int p=msg[3],r=msg[4];
    if(p<0 || p>=8 || r<0 || r>=4 || p!=claim[1] || r!=claim[2])return;
    device const int *q=request+(graph*4+r)*7,*t=parents+(graph*8+p)*9;
    if(!t[0] || t[1]<0 || t[1]>=6 || t[2]<0 || t[2]>=2)return;
    device const int *aa=a+(graph*6+t[1])*5,*bb=b+(graph*2+t[2])*2;
    if(aa[0]!=bb[0] || aa[0]!=q[2] || aa[1]!=q[3] || aa[4]!=q[6] || t[8]!=q[6])return;
    for(int i=0;i<4;i++)if(aa[i]!=t[3+i])return;
    if(bb[1]!=t[7] || claim[3]!=aa[0] || claim[4]!=aa[1] || claim[5]!=q[4]
       || claim[6]!=aa[3] || claim[7]!=bb[1])return;
    int x=cfg[6+q[5]],y=cfg[6+q[6]],mask=ctx[2*graph],edge=ctx[2*graph+1],work=0;
    bool ok=false;
    if(macro){
        int m=msg[6];if(size!=7 || m<0 || m>=cfg[3])return;
        device const int *rule=macros+6*m;work=1;
        ok=rule[0]==x && rule[1]==y && (mask&rule[2])==rule[2] && (!rule[3] || rule[3]==edge);
    }else{
        ok=replay(msg+6,size-6,cfg,rules,mask,edge,x,y,work);
    }
    result[0]=int(ok);result[1]=work;
}

kernel void publish(device const int *claims, device const int *verified, device int *outputs,
                    uint graph [[thread_position_in_grid]]) {
    int seen=0;
    for(int lane=0;lane<8;lane++){
        int id=8*graph+lane;
        if(!verified[2*id])continue;
        device const int *c=claims+8*id;int r=c[2];
        if(seen&(1<<r))continue;
        seen|=1<<r;
        device int *out=outputs+(graph*4+r)*7;
        out[0]=c[1];out[1]=r;
        for(int j=0;j<5;j++)out[j+2]=c[3+j];
    }
}
