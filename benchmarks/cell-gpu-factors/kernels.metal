#include <metal_stdlib>
#include <metal_simdgroup_matrix>
using namespace metal;

// Binary FP16 activations, FP32 dot products, threshold after EVERY product.
// The admitted reduction dimension is <= 2^24; all sums are exact integers.
struct MM { uint m,n,k,batches,ta,tb; };
kernel void boolean_mm(device const half* a [[buffer(0)]],
                       device const half* b [[buffer(1)]],
                       device half* out [[buffer(2)]],
                       constant MM& c [[buffer(3)]],
                       uint tile [[threadgroup_position_in_grid]],
                       uint lane [[thread_index_in_threadgroup]]) {
    uint cols=(c.n+7)/8, rows=(c.m+7)/8;
    uint batch=tile/(cols*rows), local=tile%(cols*rows);
    uint r0=(local/cols)*8, c0=(local%cols)*8;
    a+=batch*c.m*c.k; b+=batch*c.k*c.n; out+=batch*c.m*c.n;
    threadgroup half aa[64],bb[64]; threadgroup float result[64];
    simdgroup_float8x8 acc(0.0f);
    for(uint k0=0;k0<c.k;k0+=8) {
        for(uint j=lane;j<64;j+=32) {
            uint r=j/8,s=j%8;
            aa[j]=(r0+r<c.m && k0+s<c.k) ? a[c.ta?(k0+s)*c.m+r0+r:(r0+r)*c.k+k0+s]:half(0);
            bb[j]=(k0+r<c.k && c0+s<c.n) ? b[c.tb?(c0+s)*c.k+k0+r:(k0+r)*c.n+c0+s]:half(0);
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        simdgroup_half8x8 x,y; simdgroup_load(x,aa,8); simdgroup_load(y,bb,8);
        simdgroup_multiply_accumulate(acc,x,y,acc);
        threadgroup_barrier(mem_flags::mem_threadgroup);
    }
    simdgroup_store(acc,result,8); threadgroup_barrier(mem_flags::mem_threadgroup);
    for(uint j=lane;j<64;j+=32) {
        uint r=r0+j/8,s=c0+j%8;
        if(r<c.m && s<c.n)out[r*c.n+s]=half(result[j]>0.5f);
    }
}

// Keep the correlation at a shared row. Intersection of two rank-r Boolean
// products generally needs r*r factors, including the cross-factor pairs.
struct Pair {uint rows,rank,batches;};
kernel void pair_columns(device const half* a [[buffer(0)]],
                         device const half* b [[buffer(1)]],
                         device half* out [[buffer(2)]],
                         constant Pair& c [[buffer(3)]],uint id [[thread_position_in_grid]]) {
    if(id>=c.batches*c.rows*c.rank*c.rank)return;
    uint row=id/(c.rank*c.rank), pair=id%(c.rank*c.rank);
    out[id]=a[row*c.rank+pair/c.rank]*b[row*c.rank+pair%c.rank];
}
kernel void intersect(device const half* a [[buffer(0)]],
                      device const half* b [[buffer(1)]],
                      device half* out [[buffer(2)]],
                      constant uint& count [[buffer(3)]],uint id [[thread_position_in_grid]]) {
    if(id<count)out[id]=a[id]*b[id];
}

// One independent context per threadgroup. Stable factor columns are equality
// classes. Merging columns on BOTH sides implicitly creates both cross products.
// Parent metadata stays integer. All data updates stay GPU resident.
struct Merge {uint leftRows,rightRows,rank,batches,events;};
kernel void merge_columns(device half* left [[buffer(0)]],
                          device half* right [[buffer(1)]],
                          device uint* parent [[buffer(2)]],
                          device const uint* events [[buffer(3)]],
                          constant Merge& c [[buffer(4)]],
                          uint batch [[threadgroup_position_in_grid]],
                          uint lane [[thread_index_in_threadgroup]]) {
    left+=batch*c.leftRows*c.rank; right+=batch*c.rightRows*c.rank;
    parent+=batch*c.rank; events+=batch*c.events*2;
    threadgroup uint roots[2];
    for(uint e=0;e<c.events;e++) {
        if(lane==0) {
            uint a=events[e*2],b=events[e*2+1];
            while(parent[a]!=a)a=parent[a]; while(parent[b]!=b)b=parent[b];
            roots[0]=a; roots[1]=b;
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        uint a=roots[0],b=roots[1];
        if(a!=b) {
            for(uint row=lane;row<c.leftRows;row+=128) {
                left[row*c.rank+a]=max(left[row*c.rank+a],left[row*c.rank+b]);
                left[row*c.rank+b]=half(0);
            }
            for(uint row=lane;row<c.rightRows;row+=128) {
                right[row*c.rank+a]=max(right[row*c.rank+a],right[row*c.rank+b]);
                right[row*c.rank+b]=half(0);
            }
        }
        threadgroup_barrier(mem_flags::mem_device);
        if(lane==0 && a!=b)parent[b]=a;
        threadgroup_barrier(mem_flags::mem_device);
    }
}
