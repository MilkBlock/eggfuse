#include <metal_stdlib>
using namespace metal;
kernel void bindings(device const int *left, device const int *right,
                     device const int *tests, device const int *shape,
                     device atomic_uint *count, device int *tokens,
                     uint i [[thread_position_in_grid]]) {
    uint pair = i + uint(shape[5]);
    int group = -1, rightCount = shape[1], lw = shape[2], rw = shape[3], ntests = shape[4];
    if (shape[0] < 0) {
        // Descriptors partition the concatenated pair space of this one frozen Run.
        int lo = 0, hi = -shape[0];
        while (lo < hi) {
            int mid = lo + (hi-lo)/2;
            if (pair >= uint(tests[mid*8])) lo = mid+1; else hi = mid;
        }
        group = lo;
        device const int *desc = tests+group*8;
        pair -= group ? uint(desc[-8]) : 0;
        left += desc[1]; right += desc[2];
        rightCount = desc[3]; lw = desc[4]; rw = desc[5];
        ntests = desc[7]; tests += desc[6];
    }
    uint a = pair / uint(rightCount), b = pair % uint(rightCount);
    device const int *l = left + a * lw, *r = right + b * rw;
    if (l[0] < 0 || r[0] < 0 || !(l[0] | r[0])) return;
    for (int j = 0; j < ntests; ++j) {
        int x = tests[2*j], y = tests[2*j+1];
        int vx = x < lw ? l[x] : r[x-lw];
        int vy = y < 0 ? -1-y : (y < lw ? l[y] : r[y-lw]);
        if (vx != vy) return;
    }
    uint pos = atomic_fetch_add_explicit(count, 1u, memory_order_relaxed);
    tokens[pos*2] = group < 0 ? int(a) : group;
    tokens[pos*2+1] = group < 0 ? int(b) : int(pair);
}
