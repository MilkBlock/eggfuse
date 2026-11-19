"""Greedy FP32 Metal row body on the device. Training uses the PyTorch actor.

A SIMD group covers one graph/lane. A closed physical group returns before
reading previous-token or pointer weights. The timed dense scorer computes
ungated raw rows in a separate dispatch from publishing, so its output masking
cannot eliminate its body. Both timed modes use the same publishing dispatch.
"""
from functools import lru_cache

import torch


D = 32
PARENTS = 8


def _score_kernel(physical, audit):
    name = ('score_physical' if physical else 'score_dense') + ('_audit' if audit else '')
    audit_args = 'device int *executed, device float *energy,' if audit else ''
    on_skip = 'if (lane == 0) { executed[row] = 0; energy[row] = 0; }' if audit else ''
    early_return = f'if (!gate[row]) {{ {on_skip} return; }}' if physical else ''
    audit_start = 'float work = simd_sum(h*h) + a0*a0 + a1*a1;' if audit else ''
    audit_score = 'work += score*score;' if audit else ''
    audit_finish = 'if (lane == 0) { executed[row] = 1; energy[row] = work; }' if audit else ''
    return f'''
    kernel void {name}(
        device const uchar *gate, device const float *base, device const float *previous,
        device const float *wh, device const float *wq, device const float *wa, device const float *ba,
        device const float *ports, device const float *left_key, device const float *right_key,
        device const float *right_condition, device const int *left, device const int *right,
        device float *raw, {audit_args} constant int *cfg, constant float &scale,
        uint row [[threadgroup_position_in_grid]], uint lane [[thread_index_in_simdgroup]]) {{
        {early_return}
        const int length=cfg[1], pos=cfg[2], w=cfg[3], nl=cfg[4], nr=cfg[5];
        const int lw=cfg[6], rw=cfg[7], cols=cfg[8];
        const uint graph=row/uint(cfg[0]);
        const uint record=row*uint(w+2+nl+nr+3);
        float z=0;
        for (int i=0; i<w; ++i) z=fma(wh[lane*w+i], previous[row*w+i], z);
        float h=tanh(base[(row*length+pos)*32+lane]+z);
        raw[record+lane]=h;
        float a0=simd_sum(h*wa[lane])+ba[0];
        float a1=simd_sum(h*wa[32+lane])+ba[1];
        int active=a1>a0;
        if (lane==0) {{raw[record+w]=a0; raw[record+w+1]=a1;}}
        {audit_start}
        float with_port=h+ports[(graph*2)*32+lane];
        float q=0;
        for (ushort k=0;k<32;++k) q=fma(wq[lane*32+k], simd_shuffle(with_port,k),q);
        int li=0,ri=0; float best=-INFINITY;
        for (int j=0;j<nl;++j) {{
            float score=simd_sum(q*left_key[(graph*nl+j)*32+lane])*scale;
            if(lane==0) raw[record+w+2+j]=score;
            if(score>best) {{li=j;best=score;}}
            {audit_score}
        }}
        with_port=(h+ports[(graph*2+1)*32+lane])+right_condition[(graph*nl+li)*32+lane];
        q=0;
        for (ushort k=0;k<32;++k) q=fma(wq[lane*32+k], simd_shuffle(with_port,k),q);
        best=-INFINITY;
        for (int j=0;j<nr;++j) {{
            float score=simd_sum(q*right_key[(graph*nr+j)*32+lane])*scale;
            if(lane==0) raw[record+w+2+nl+j]=score;
            if(score>best) {{ri=j;best=score;}}
            {audit_score}
        }}
        if(lane==0) {{
            const uint start=record+w+2+nl+nr;
            raw[start]=float(active); raw[start+1]=float(li); raw[start+2]=float(ri);
        }}
        for(int j=lane;j<w-32;j+=32) {{
            float v=0;
            if(j<2) v=float(j==active);
            else if(j<10) v=float(j-2==li);
            else if(j<18) v=float(j-10==ri);
            else if(j-18<cols) {{
                int side=cfg[9+2*(j-18)], col=cfg[10+2*(j-18)];
                if(side==0) v=float(left[(graph*nl+li)*lw+col]);
                else if(side==1) v=float(right[(graph*nr+ri)*rw+col]);
                else v=float(col);
            }}
            raw[record+32+j]=v;
        }}
        {audit_finish}
    }}
    '''


_PUBLISH = '''
kernel void publish_rows(device const uchar *gate, device const float *raw, device float *next,
                         device float *scores, device long *discrete, constant int *cfg,
                         uint row [[threadgroup_position_in_grid]], uint lane [[thread_index_in_simdgroup]]) {
    bool open=gate[row]!=0;
    int w=cfg[3], width=2+cfg[4]+cfg[5], cols=cfg[8];
    uint start=row*uint(w+width+3);
    for(int i=lane;i<w;i+=32) next[row*w+i]=open?raw[start+i]:0;
    for(int i=lane;i<width;i+=32) scores[row*width+i]=open?raw[start+w+i]:0;
    for(int i=lane;i<3+cols;i+=32) {
        int offset=i<3 ? w+width+i : 32+18+i-3;
        discrete[row*(3+cols)+i]=open ? long(raw[start+offset]) : 0;
    }
}
'''


@lru_cache(maxsize=1)
def metal_library():
    source = '#include <metal_stdlib>\nusing namespace metal;\n'
    source += '\n'.join(_score_kernel(physical, audit) for physical in (False, True) for audit in (False, True))
    lib = torch.mps.compile_shader(source + _PUBLISH)
    if lib.score_physical.thread_execution_width != D:
        raise RuntimeError('this lane kernel requires 32 threads per Apple SIMD group')
    return lib


class MetalStage:
    def __init__(self, decoder, left, right, left_features, right_features, ports, routes, rule_id, rows):
        if decoder.dim != D or decoder.slots != PARENTS or decoder.max_columns != 5:
            raise ValueError('expected Figure 05 decoder with width 32, eight slots and five projected columns')
        if rows not in (1, 2, 4) or not (1 <= len(routes) <= decoder.max_columns):
            raise ValueError('unsupported row or projection count')
        if left.ndim != 3 or right.ndim != 3 or left.shape[0] != right.shape[0] or not left.shape[0]:
            raise ValueError('expected two nonempty batched source tables')
        if not all(1 <= tensor.shape[1] <= PARENTS and tensor.shape[-1] > 0 for tensor in (left, right)):
            raise ValueError('source rows exceed Figure 05 pointer capacity')
        if left.dtype not in (torch.int32,torch.int64) or right.dtype not in (torch.int32,torch.int64):
            raise ValueError('expected source tables of small integer fields')
        if (left_features.shape != (*left.shape[:2],D) or right_features.shape != (*right.shape[:2],D)
                or ports.shape != (left.shape[0],2,D)):
            raise ValueError('source features or port conditions have the wrong dimensions')
        if (left.device.type != 'mps' or right.device != left.device
                or any(x.device != left.device or x.dtype != torch.float32 for x in (left_features,right_features,ports))):
            raise ValueError('Metal row execution requires colocated FP32 MPS features')
        for side, column in routes:
            if side not in (0, 1, 2) or type(column) is not int:
                raise ValueError('invalid compiled column route')
            if side != 2 and not 0 <= column < (left.shape[-1],right.shape[-1])[side]:
                raise ValueError('projection exceeds source row width')
            if side == 2 and not -2**24 <= column <= 2**24:
                raise ValueError('expected an exactly representable small integer literal')
        self.lib = metal_library()
        self.device = left.device
        self.rows = rows
        self.length = decoder.slots // rows
        self.batch = left.shape[0]
        self.token_width = decoder.token_width
        self.nl, self.nr = left.shape[1], right.shape[1]
        self.cols = len(routes)
        self.row_dtype = torch.promote_types(left.dtype, right.dtype)
        self.score_width = 2 + self.nl + self.nr
        self.head = decoder.heads[0 if decoder.shared_heads else rule_id]
        if self.head.query.weight.shape != (D,D) or self.head.key.weight.shape != (D,D):
            raise ValueError('this Metal kernel requires the original Figure 05 pointer factor widths')
        pool = decoder.pool(torch.cat((left_features.mean(1), right_features.mean(1),
                                      ports[:, 0], ports[:, 1]), dim=-1))
        self.base = (pool[:, None, None] + decoder.position.weight.reshape(rows, self.length, D)).contiguous()
        # These caches are charged once per Run and cover all source candidates.
        # The condition projection is moved outside the per-lane pointer body.
        self.buffers = (decoder.history.weight.contiguous(), self.head.query.weight.contiguous(),
                        decoder.active.weight.contiguous(), decoder.active.bias.contiguous(), ports.contiguous(),
                        self.head.key(left_features).contiguous(), self.head.key(right_features).contiguous(),
                        decoder.condition_right(left_features).contiguous(),
                        left.to(torch.int32).contiguous(), right.to(torch.int32).contiguous())
        route = [field for pair in routes for field in pair]
        self.configs = [[rows, self.length, t, self.token_width, self.nl, self.nr, left.shape[-1],
                         right.shape[-1], self.cols, *route] for t in range(self.length)]

    def step(self, t, gate, previous, *, physical, audit=False):
        """Return (stage outputs, next token). Closed physical groups skip the scored body."""
        if torch.is_grad_enabled():
            raise RuntimeError('custom Metal row dispatch is inference-only')
        shape = (self.batch, self.rows)
        if gate.device != self.device or gate.shape != shape or gate.dtype not in (torch.bool, torch.int32, torch.uint8):
            raise ValueError('gate must be a device-local [batch,rows] boolean or integer bit')
        if previous.shape != (*shape, self.token_width) or previous.device != self.device or previous.dtype != torch.float32:
            raise ValueError('previous must be a device-local FP32 row token')
        if not 0 <= t < self.length:
            raise ValueError('round outside fixed slot layout')
        gate_bytes = gate.to(torch.uint8).contiguous()
        cfg = self.configs[t]
        raw = self.base.new_empty((*shape,self.token_width+self.score_width+3))
        trace = {}
        aux = []
        if audit:
            trace['executed'] = torch.empty(shape, dtype=torch.int32, device=self.device)
            trace['work_checksum'] = self.base.new_empty(shape)
            aux = [trace['executed'], trace['work_checksum']]
        name = ('score_physical' if physical else 'score_dense') + ('_audit' if audit else '')
        kernel = getattr(self.lib, name)
        # The config is a packed int32 array; the following scale is a scalar FP32.
        launch = dict(threads=self.batch*self.rows*D, group_size=D, arg_casts={14+len(aux): 'int32'})
        kernel(gate_bytes,self.base,previous.contiguous(),*self.buffers,raw,*aux,cfg,self.head.scale,**launch)
        next_token = torch.empty_like(previous, memory_format=torch.contiguous_format)
        scores = self.base.new_empty((*shape,self.score_width))
        discrete = torch.empty((*shape,3+self.cols), dtype=torch.int64, device=self.device)
        self.lib.publish_rows(gate_bytes,raw,next_token,scores,discrete,cfg,
                              threads=self.batch*self.rows*D,group_size=D,arg_casts={5:'int32'})
        projected = discrete[...,3:].to(self.row_dtype)
        stage = dict(hidden=next_token[...,:D], active_logits=scores[...,:2],
                     left_logits=scores[...,2:2+self.nl], right_logits=scores[...,2+self.nl:],
                     active=discrete[...,0], pointers=discrete[...,1:3], rows=projected,
                     fields=projected[...,2:], **trace)
        return stage, next_token


@torch.no_grad()
def prepare_metal_stage(decoder, left, right, left_features, right_features, ports, routes, rule_id=0, rows=2):
    return MetalStage(decoder,left,right,left_features,right_features,ports,routes,rule_id,rows)
