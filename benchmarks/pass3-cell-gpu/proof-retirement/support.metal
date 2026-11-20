#include <metal_stdlib>
using namespace metal;
kernel void withdraw(device const int *proof,device const int *roots,device const int *first,
                     device const int *suppliers,device const int *outputs,device const int *fact_ids,
                     device int *out,device int *scratch,device int *metrics,
                     constant int &n,constant int &facts,constant int &mode,uint h [[thread_position_in_grid]]){
    device int *lost=out+h*n;
    int damaged=roots[h];lost[damaged]=proof[4*damaged]; // withdrawal at the original issue boundary
    bool progress=true;
    while(progress){
        progress=false;
        for(int i=0;i<n;i++){
            int issue=proof[4*i],release=proof[4*i+1],parent=proof[4*i+2],when=lost[i];
            if(parent>=0 && lost[parent]){
                int candidate=max(issue,lost[parent]);
                if(candidate<=release && (!when || candidate<when))when=candidate;
            }
            if(mode==0)for(int j=0;j<n;j++){
                // The verifier may still retire pending siblings until their source Run publishes.
                int other=lost[j];
                if(other && proof[4*j]==issue && other<=release && (!when || other<when))when=other;
            }
            if(when!=lost[i]){lost[i]=when;progress=true;}
        }
    }
    int absent=0,uncertain=0,saved=0,rechecks=0,previous=0,survivors=0;
    device int *invalid=scratch+h*facts;
    for(int i=0;i<n;i++)if(lost[i]){
        for(int k=outputs[i];k<outputs[i+1];k++){
            int f=fact_ids[k];if(mode==2)invalid[f]++;else invalid[f]=1;
        }
    }
    for(int f=0;f<facts;f++){
        if(!invalid[f])continue;
        if(mode==2){
            int total=first[f+1]-first[f];
            if(invalid[f]==total)absent++;else saved++;
            continue;
        }
        uncertain++;
        bool found=false;
        for(int k=first[f];k<first[f+1];k++){
            rechecks++;if(!lost[suppliers[k]]){found=true;break;}
        }
        absent+=int(!found);
    }
    for(int i=0;i<n;i++)if(lost[i])previous++;else survivors++;
    device int *m=metrics+6*h;m[0]=previous;m[1]=survivors;m[2]=absent;
    m[3]=uncertain;m[4]=saved;m[5]=rechecks;
}
