#include <metal_stdlib>
using namespace metal;

// A candidate row stores a visibility bit followed by bucket IDs of its ports.
// Descriptors and candidate banks are independent of the exact CPU key index.
kernel void propose_parent(device const int *anchors, device const int *parents,
                           constant int *cfg, constant int *cols,
                           device const float *weights, device int *out,
                           uint i [[thread_position_in_grid]]) {
    device const int *a = anchors + i*cfg[0];
    int best = -1;
    float high = weights[PORT_BOOKS*128*PORT_DIM];
    if (a[0]) {
        for (int p=0; p<cfg[2]; p++) {
            device const int *row = parents + p*cfg[1];
            if (!row[0]) continue;
            float score = 0;
            for (int k=0; k<cfg[3]; k++) {
                int c = cols[k];
                int q = c<0 ? -1-c : a[c+1];
                int v = row[k+1];
                for (int book=0; book<PORT_BOOKS; book++) {
                    int qbase=PORT_DIM*(book*128+((q>>(7*book))&127));
                    int vbase=PORT_DIM*(book*128+((v>>(7*book))&127));
                    for (int d=0; d<PORT_DIM; d++) score+=weights[qbase+d]*weights[vbase+d];
                }
            }
            score /= float(cfg[3]*PORT_BOOKS);
            if (score>high) { high=score; best=p; }
        }
    }
    out[i]=best;
}
