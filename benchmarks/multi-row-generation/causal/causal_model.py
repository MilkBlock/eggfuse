"""Causal generated-token decoder with explicit per-stage K/V caches.

Uses the SAME parameter shapes as Generator. A serial token sees actual earlier
outputs in its stage, not teacher outputs or hypothetical future queries.
"""
import sys
from pathlib import Path
import numpy as np
import mlx.core as mx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network import Generator as BaseGenerator
from task import TEMPLATES


class CausalGenerator(BaseGenerator):
    def __init__(self):super().__init__('joint')

    def stage(self,source,memory,source_positions,memory_positions,output_positions,phase,rows,length,grouping,erase_history=False,erase_after=None):
        n=rows*length
        if grouping=='serial':groups=[[i] for i in range(n)]
        elif grouping=='rows':groups=[[r*length+t for r in range(rows)] for t in range(length)]
        elif grouping=='block':groups=[list(range(n))]
        else:raise ValueError(grouping)
        template=self.template_encoder(mx.array(TEMPLATES[phase]))
        template=mx.broadcast_to(template,source.shape)
        external_kv=self.pointer.prepare_memory(self.norm(memory),memory_positions)
        known=self.norm(source)
        known_kv=self.query_mix.prepare_memory(known,source_positions)
        history=None;out_p=[];out_h=[];out_f=[];order=[]
        for at,indices in enumerate(groups):
            ids=mx.array(indices,mx.int32);current=source[:,ids];q=known[:,ids];pos=source_positions[ids]
            context_kv=known_kv if history is None else tuple(mx.concatenate((k,h),axis=-2) for k,h in zip(known_kv,history))
            _,context=self.query_mix.from_prepared(q,pos,context_kv)
            q=self.query(mx.concatenate((self.norm(current+context),template[:,ids]),-1))
            scores,latent,fields=self.emit((q,external_kv,template[:,ids],pos))
            out_p.append(scores);out_h.append(latent);out_f.append(fields);order.extend(indices)
            if at+1<len(groups):
                erase=erase_history or (erase_after is not None and at>=erase_after)
                new_kv=self.query_mix.prepare_memory(self.norm(mx.zeros_like(latent) if erase else latent),output_positions[ids])
                history=new_kv if history is None else tuple(mx.concatenate((h,v),axis=-2) for h,v in zip(history,new_kv))
        inverse=mx.array(np.argsort(order).astype(np.int32))
        return tuple(mx.concatenate(v,axis=1)[:,inverse] for v in (out_p,out_h,out_f))

    def forward_grouped(self,a,b,pa,pb,length,rows,rounds=2,grouping='serial'):
        a=self.encoder(a);b=self.encoder(b);p=[];h=[];f=[];addresses=[]
        for step in range(rounds):
            source,memory=(a,b) if step==0 else (h[-1],h[-1])
            source_pos=pa if step==0 else pa+mx.array([0,(step+1)*length],mx.int32)
            memory_pos=pb if step==0 else source_pos
            output_pos=pa+mx.array([0,(step+2)*length],mx.int32)
            scores,latent,fields=self.stage(source,memory,source_pos,memory_pos,output_pos,int(step>0),rows,length,grouping)
            pointer=mx.stop_gradient(mx.argmax(scores,-1));p.append(scores);h.append(latent);f.append(fields);addresses.append(memory_pos[pointer])
        return dict(pointer_logits=mx.stack(p),latent=mx.stack(h),field_logits=mx.stack(f),addresses=mx.stack(addresses),pointers=mx.stop_gradient(mx.argmax(mx.stack(p),-1)))
