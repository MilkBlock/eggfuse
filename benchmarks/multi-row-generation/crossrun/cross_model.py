"""Two rules share an on-device token boundary. CPU labels never enter forward."""
from pathlib import Path
import sys
import json
import mlx.core as mx
import mlx.nn as nn

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / 'streaming'))
from stream_model import StreamGenerator, hard_symbol, token
from network import Attention, DIM
from data import K, V, N, Q, FEATURES


def projection_recipe(path):
    rules = json.loads(Path(path).read_text())['rules']
    maps = []
    for stage, tables in [('make', ('A', 'B')), ('finish', ('Pair', 'Request'))]:
        rule = rules[stage]
        if set(rule['inputs']) != set(tables) or len(rule['outputs']) != 5:
            raise ValueError(f'unsupported {stage} interface')
        maps.append(tuple((tables.index(rule['inputs'][side]), col) for side, col in rule['outputs']))
    return tuple(maps)


def scores_to_fields(scores):
    return mx.stack([mx.argmax(scores[..., lo:hi], -1) for lo, hi in ((0, K), (K, K+V), (K+V, K+2*V))], -1)


def select(rows, indices):
    return mx.take_along_axis(rows, indices[..., None], axis=1)


def project(left, right, pointer, routes):
    indices = mx.stop_gradient(mx.argmax(pointer[0], -1)), mx.stop_gradient(mx.argmax(pointer[1], -1))
    selected = select(left, indices[0]), select(right, indices[1])
    return mx.stack([selected[side][..., column] for side, column in routes], -1)


def as_logits(fields):
    # Integer selection is exact. token() takes the argmax of each group.
    return mx.concatenate([mx.eye(w)[fields[..., i]] for i, w in enumerate((K,V,V))], -1)


def inputs(a, b):
    def table(x, kind):
        identity = mx.broadcast_to(mx.arange(N)[None,:,None], x.shape[:2]+(1,))
        raw = mx.concatenate((identity, x), -1)
        tag = mx.broadcast_to(mx.eye(2)[kind], x.shape[:2]+(2,))
        encoded = mx.concatenate((mx.eye(K)[x[...,0]],mx.eye(V)[x[...,1]],tag), -1)
        return raw, encoded
    ar, af = table(a,0)
    br, bf = table(b,1)
    return ar, br, mx.concatenate((af,bf),1)


class Make(StreamGenerator):
    def emit_fields(self, h, pointers, rows, plan, static):
        if static:
            projected = project(*rows, pointers, plan)
            return as_logits(projected[...,2:])
        return self.fields(h)

    def produce(self, x, source_rows, sp, op, routes, static):
        # Same two causal rounds as the historical 4x2 feedback decoder.
        source = self.encoder(x)
        source_kv = [b.source.prepare_memory(source,sp) for b in self.blocks]
        lk = self.left.prepare_memory(source[:,:N],sp[:N])
        rk = self.right.prepare_memory(source[:,N:],sp[N:])
        cache = [None]*len(self.blocks)
        parts = []
        for t in range(2):
            ids = mx.array([2*r+t for r in range(4)])
            pos = op[ids]
            q = self.row(pos[:,0])+self.position(mx.full((4,),t,mx.int32))
            q = mx.broadcast_to(q,(x.shape[0],4,DIM))
            for i, block in enumerate(self.blocks):
                q = block(q,pos,source_kv[i],cache[i],None)
            h = self.norm(q)
            left,_ = self.left.from_prepared(h,pos,lk)
            right,_ = self.right.from_prepared(h,pos,rk)
            active = self.active(h)
            pointer = mx.stack((left,right),2)
            fields = self.emit_fields(h,(left,right),source_rows,routes,static)
            emitted = token(h,active,pointer,fields)
            parts.append((h,active,left,right,fields,emitted))
            if t == 0:
                history = self.history_encoder(emitted)
                cache = [block.history.prepare_memory(block.norm(history),pos) for block in self.blocks]
        inverse = mx.array([0,4,1,5,2,6,3,7])
        return tuple(mx.concatenate(xs,1)[:,inverse] for xs in zip(*parts))


class Finish(nn.Module):
    def __init__(self):
        super().__init__()
        self.pair = nn.Linear(90,DIM)
        self.request = nn.Linear(2*N+V,DIM)
        self.slot = nn.Embedding(Q,DIM)
        self.read = Attention()
        self.mix = Attention()
        self.left = Attention()
        self.right = Attention()
        self.norm = nn.LayerNorm(DIM)
        self.ff = nn.Sequential(nn.Linear(DIM,2*DIM),nn.GELU(),nn.Linear(2*DIM,DIM))
        self.active = nn.Linear(DIM,2)
        self.fields = nn.Linear(DIM,K+2*V)

    def __call__(self, emitted, req, pp, rp, op, routes, static, mask):
        keep = [1.]*90
        if mask in ('parents','parents_latent'):
            keep[66:74] = [0.]*8
        if mask == 'parents_latent':
            keep[:64] = [0.]*64
        visible = emitted * mx.array(keep)
        pair = self.pair(visible)
        requests = self.request(mx.concatenate([mx.eye(w)[req[...,i]] for i,w in enumerate((N,N,V))],-1))
        q = mx.broadcast_to(self.slot(mx.arange(Q)),pair.shape)
        _,z = self.read(q,mx.concatenate((pair,requests),1),op,mx.concatenate((pp,rp),0))
        q = self.norm(q+z)
        _,z = self.mix(q,q,op,op)
        h = self.norm(q+z+self.ff(q+z))
        l,_ = self.left(h,pair,op,pp)
        r,_ = self.right(h,requests,op,rp)
        if static:
            pair_columns = mx.stack([mx.argmax(visible[...,i:j],-1) for i,j in ((66,70),(70,74),(74,82),(82,86),(86,90))],-1)
            projected = project(pair_columns,req,(l,r),routes)
            fields = as_logits(projected[...,2:])
        else:
            fields = self.fields(h)
        return h,self.active(h),l,r,fields


class CrossRun(nn.Module):
    def __init__(self,arm,plan):
        super().__init__()
        self.make = Make('feedback')
        self.finish = Finish()
        self.arm = arm
        # Python-only immutable metadata avoids trainable array registration.
        self.make_routes,self.finish_routes = plan

    def __call__(self,a,b,req,mask='none',training_heads=False):
        ar,br,x = inputs(a,b)
        sp = mx.array([[i//2,i%2] for i in range(8)])
        pp = sp + mx.array([0,2])
        rp = sp[:4] + mx.array([0,4])
        op = sp + mx.array([0,6])
        static = self.arm != 'learned'
        h1,active1,l1,r1,f1,emitted = self.make.produce(x,(ar,br),sp,pp,self.make_routes,static)
        h2,active2,l2,r2,f2 = self.finish(emitted,req,pp,rp,op,self.finish_routes,static,mask)
        out = [(active1,l1,r1,f1),(active2,l2,r2,f2)]
        if training_heads and self.arm=='aux':
            out = [(active1,l1,r1,self.make.fields(h1)),(active2,l2,r2,self.finish.fields(h2))]
        return out,emitted


def decode(outputs):
    return [dict(active=mx.argmax(active,-1),pointers=mx.stack((mx.argmax(left,-1),mx.argmax(right,-1)),-1),fields=scores_to_fields(fields)) for active,left,right,fields in outputs]
