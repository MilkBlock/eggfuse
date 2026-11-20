#include <metal_stdlib>
using namespace metal;

kernel void root_latents(device const float *features,device const float *weights,device const float *bias,
                         device float *output,uint gid [[thread_position_in_grid]]){
    int component=gid%12,parent=gid/12;
    float sum=bias[component];
    for(int j=0;j<6;j++)sum+=features[6*parent+j]*weights[6*component+j];
    output[gid]=tanh(sum);
}

// One SIMD group computes the 32 hidden channels for a candidate and reduces its final logit.
kernel void child_scores(device const float *parents,device const float *features,device const int *catalog,
                         device const float *tables,device const float *rules,device const float *weights,
                         device const float *bias,device const float *final_weights,device const float *final_bias,
                         device float *scores,uint lane [[thread_index_in_simdgroup]],uint gid [[threadgroup_position_in_grid]]){
    device const int *entry=catalog+7*gid;
    device const float *w=weights+40*lane;
    float x=bias[lane];
    for(int j=0;j<12;j++)x+=w[j]*parents[12*entry[0]+j];
    for(int j=0;j<12;j++)x+=w[12+j]*features[12*gid+j];
    for(int j=0;j<8;j++)x+=w[24+j]*tables[8*entry[5]+j];
    for(int j=0;j<8;j++)x+=w[32+j]*rules[8*entry[2]+j];
    float logit=simd_sum(tanh(x)*final_weights[lane]);
    if(lane==0)scores[gid]=logit+final_bias[0];
}
