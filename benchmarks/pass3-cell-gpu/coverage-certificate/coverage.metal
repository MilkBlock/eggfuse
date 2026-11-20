// One predicate for both Metal and the native CPU checker. Only the invocation
// and pointer address space differ. All inputs are signed 64-bit words.
#ifdef EGGFUSE_CPU_CHECK
#include <cstdint>
using ulong = unsigned long;
#define GLOBAL
static_assert(sizeof(long)==8 && sizeof(int)==4);
#else
#include <metal_stdlib>
using namespace metal;
#define GLOBAL device
#endif

// Result 0 is accepted, 1 is an illegal token, 2 is an uncovered member.
inline int check_member(GLOBAL const long *domain, GLOBAL const long *tokens,
                        GLOBAL const long *config, unsigned i){
    const long n=config[0],initial=config[1],increment=config[2];
    GLOBAL const long *node=tokens+5*i;
    if(node[0]==0)return 2;
    bool good=node[0]==1 && node[1]==domain[2*i] && node[3]>=0 && node[3]<n;
    if(i==0)good &= node[2]==-1 && node[3]==0 && node[4]==initial;
    else if(node[2]<0 || node[2]>=n)good=false;
    else {
        GLOBAL const long *parent=tokens+5*node[2];
        good &= parent[0]==1 && parent[1]==domain[2*i+1] && parent[3]>=0 && parent[3]<n &&
                parent[3]+1==node[3] && ulong(parent[4])+ulong(increment)==ulong(node[4]);
    }
    return good?0:1;
}

#ifdef EGGFUSE_CPU_CHECK
extern "C" void certify_cpu(const long *domain,const long *tokens,const long *config,int *verdict){
    for(unsigned i=0;i<config[0];i++){
        int result=check_member(domain,tokens,config,i);
        verdict[2*i]=result==1;
        verdict[2*i+1]=result==2;
    }
}
#else
kernel void certify(device const long *domain,device const long *tokens,device const long *config,
                    device int2 *verdict,uint i [[thread_position_in_grid]]){
    int result=check_member(domain,tokens,config,i);
    verdict[i]=int2(result==1,result==2);
}
#endif
