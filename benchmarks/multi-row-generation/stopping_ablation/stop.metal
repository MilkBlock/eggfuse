#include <metal_stdlib>
using namespace metal;

// Persistent ledger: phase, age, flight mask, inbox mask, dirty congruence,
// pending delta, sealed, previous mutation, phase admission flag, ticks,
// receipt work, scans, delta propagations, idle turns, close attempts, vetoes,
// unsound closes, stalled ready ticks, forced work, peak stall, current stall,
// observations, closure probes, policy calls. Per-phase outputs retained.
constant int W=24;
inline bool merge_classes(device int *c,int n,int a,int b){
    int x=c[a],y=c[b];if(x==y)return false;
    int old=max(x,y),fresh=min(x,y);
    for(int j=0;j<n;j++)if(c[j]==old)c[j]=fresh;
    return true;
}
inline void observe(device const int *c,device const int *plan,device const int *req,
                    device const int *source,device int *out,uint graph,int phase){
    // Six representatives + four (physical parent, RHS columns[5]) rows.
    device int *v=out+(graph*3+phase)*30;
    for(int j=0;j<6;j++)v[j]=c[plan[2+j]];
    for(int j=0;j<4;j++){
        int q=graph*4+j;
        bool live=c[req[2*q]]==c[req[2*q+1]] && source[6*q]>=0;
        for(int k=0;k<6;k++)v[6+j*6+k]=live?source[6*q+k]:-1;
    }
}
inline int predict(device const float *w,thread const float *x){
    float y[3]={w[120],w[121],w[122]};
    for(int j=0;j<12;j++){
        float h=w[72+j];
        for(int k=0;k<6;k++)h+=w[j*6+k]*x[k];
        h=max(h,0.0f);
        for(int k=0;k<3;k++)y[k]+=w[84+k*12+j]*h;
    }
    return y[1]>y[0]?(y[2]>y[1]?2:1):(y[2]>y[0]?2:0);
}
kernel void advance(device int *classes,device int *state,device const int *manifest,
                    device const int *plan,device const int *req,device const int *source,
                    device const float *weights,device int *visible,device int *boundary,
                    device int *trace,device int *index,constant int *cfg,uint g [[thread_position_in_grid]]){
    // cfg = policy, fixed slice K, additional ticks, record trace, capacity, blind.
    int mode=cfg[0],n=plan[0];device int *s=state+g*W,*c=classes+g*n;
    device int *published_index=index+g*n;
    if(!s[9] && !s[8])observe(published_index,plan,req,source,visible,g,0);
    for(int iter=0;iter<cfg[2] && s[0]<2;iter++){
        int phase=s[0];
        device const int *events=manifest+(g*2+phase)*10;
        if(!s[8]){
            s[2]=0;
            for(int j=0;j<3;j++)if(events[j*3]>=0)s[2]|=(1<<j);
            s[8]=1;
        }
        for(int j=0;j<3;j++)if((s[2]&(1<<j)) && events[j*3+2]<=s[1]){
            s[2]^=1<<j;s[3]|=1<<j;
        }
        s[6]=int(s[1]>=events[9]); // no later sends; prior sends can still be in flight
        bool ready=s[3]||s[4]||s[5];
        bool safe=!ready && !s[2] && s[6];
        int ideal=ready?0:(safe?2:1); // work, wait, close
        float x[6]={float(popcount(uint(s[3])))/3.0f,float(s[4]),float(s[5]),float(s[7]),
                    float(popcount(uint(s[2])))/3.0f,float(s[6])};
        int act=ideal;
        if(mode>=2){
            if(cfg[5]){x[4]=0;x[5]=0;}
            act=predict(weights,x);s[23]++;
        }
        int proposed=act;
        if(cfg[3] && s[9]<cfg[4]){
            device int *t=trace+(g*cfg[4]+s[9])*11;
            for(int k=0;k<6;k++)t[k]=int(round(x[k]*3));
            t[6]=ideal;t[7]=proposed;t[8]=phase;t[9]=s[1];t[10]=int(safe);
        }
        if(mode==4 && ready && act!=0 && s[20]>=2){act=0;s[18]++;}
        bool changed=false;
        if(act==0 && s[3]){
            int j=ctz(uint(s[3]));s[3]^=1<<j;s[10]++;
            changed=merge_classes(c,n,events[3*j],events[3*j+1]);
            if(changed){s[4]=1;s[5]=1;}
        }else if(act==0 && s[4]){
            int at=8;s[11]++;
            for(int j=0;j<plan[1];j++){
                int a=plan[at++],b=plan[at++],arity=plan[at++];
                bool ok=c[a]!=c[b];
                for(int k=0;k<arity;k++,at+=2)ok &= c[plan[at]]==c[plan[at+1]];
                if(ok)changed|=merge_classes(c,n,a,b);
            }
            s[4]=int(changed);if(changed)s[5]=1;
        }else if(act==0 && s[5]){for(int j=0;j<n;j++)published_index[j]=c[j];s[5]=0;s[12]++;}
        else s[13]++;
        s[7]=int(changed);
        if(ready && act!=0){s[17]++;s[20]++;s[19]=max(s[19],s[20]);}else s[20]=0;
        s[1]++;s[9]++;
        bool closed=!s[2]&&!s[3]&&!s[4]&&!s[5]&&s[6];
        bool attempt=mode==0?(s[1]%cfg[1]==0):(mode==1?closed:(act==2));
        if(attempt){
            s[14]++;s[22]++;
            if(!closed && mode!=3){s[15]++;continue;}
            if(!closed)s[16]++;
            device int *log=boundary+(g*2+phase)*8;
            log[0]=s[9];log[1]=s[2];log[2]=s[3];log[3]=s[4];log[4]=s[5];
            log[5]=s[6];log[6]=int(closed);log[7]=s[1];
            observe(published_index,plan,req,source,visible,g,phase+1);s[21]++;
            s[0]++;for(int k=1;k<=8;k++)s[k]=0;
            s[20]=0;
        }
    }
}
