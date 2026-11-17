"""Shared neural multi-row decoder. Stage 2 consumes generated latent, not labels."""
import mlx.core as mx
import mlx.nn as nn
from task import KEYS,VALUES,FEATURES,TEMPLATES

DIM=64

def rope(x,coords):
    # Each half is an independent rotary axis: row / within-row token position.
    width=x.shape[-1]//2
    freq=mx.exp(-mx.log(mx.array(10000.))*mx.arange(width//2)/ (width//2))
    pieces=[]
    for axis in range(2):
        part=x[...,axis*width:(axis+1)*width]
        angle=coords[...,axis,None].astype(mx.float32)*freq
        even,odd=part[...,0::2],part[...,1::2]
        pieces.append(mx.stack((mx.cos(angle)*even-mx.sin(angle)*odd,mx.sin(angle)*even+mx.cos(angle)*odd),-1).reshape(part.shape))
    return mx.concatenate(pieces,-1)


class Attention(nn.Module):
    def __init__(self):
        super().__init__();self.q=nn.Linear(DIM,DIM,bias=False);self.k=nn.Linear(DIM,DIM,bias=False)
        self.v=nn.Linear(DIM,DIM,bias=False);self.pq=nn.Linear(DIM,32,bias=False);self.pk=nn.Linear(DIM,32,bias=False)
        self.position_scale=mx.array(.1)
    def prepare_memory(self,m,mpos):
        return self.k(m),self.v(m),rope(self.pk(m),mpos)
    def from_prepared(self,q,qpos,memory,mask=None):
        k,v,pk=memory
        scores=(self.q(q)@mx.swapaxes(k,-1,-2))/(DIM**.5)
        scores+=self.position_scale*(rope(self.pq(q),qpos)@mx.swapaxes(pk,-1,-2))/(32**.5)
        if mask is not None:scores=mx.where(mask,scores,-1e9)
        probs=mx.softmax(scores,axis=-1)
        return scores,probs@v
    def __call__(self,q,m,qpos,mpos,mask=None):
        return self.from_prepared(q,qpos,self.prepare_memory(m,mpos),mask)



class Generator(nn.Module):
    def __init__(self,mode='joint'):
        super().__init__()
        if mode not in ('joint','independent'):raise ValueError(mode)
        self.mode=mode
        self.encoder=nn.Sequential(nn.Linear(FEATURES,DIM),nn.GELU(),nn.Linear(DIM,DIM))
        self.template_encoder=nn.Sequential(nn.Linear(8,DIM),nn.Tanh())
        self.norm=nn.LayerNorm(DIM)
        self.query_mix=Attention();self.pointer=Attention()
        self.query=nn.Sequential(nn.Linear(2*DIM,DIM),nn.GELU(),nn.Linear(DIM,DIM))
        self.transition_net=nn.Sequential(nn.Linear(3*DIM,2*DIM),nn.GELU(),nn.Linear(2*DIM,DIM))
        self.decoder=nn.Linear(DIM,2*KEYS+2*VALUES)

    def prepare(self,source,memory,source_pos,memory_pos,phase):
        template=self.template_encoder(mx.array(TEMPLATES[phase]))
        template=mx.broadcast_to(template,source.shape)
        q=self.norm(source)
        mask=None
        if self.mode=='independent':mask=source_pos[:,0,None]==source_pos[None,:,0]
        _,context=self.query_mix(q,q,source_pos,source_pos,mask)
        q=self.query(mx.concatenate((self.norm(source+context),template),-1))
        return q,self.pointer.prepare_memory(self.norm(memory),memory_pos),template,source_pos

    def emit(self,prepared):
        q,memory,template,qpos=prepared
        scores,read=self.pointer.from_prepared(q,qpos,memory)
        latent=self.norm(q+self.transition_net(mx.concatenate((q,read,template),-1)))
        return scores,latent,self.decoder(latent)

    def forward(self,a,b,pos_a,pos_b,pos_pair,erase_first=False):
        # One graph dimension contains n row sequences; batch dimension is separate.
        a=self.encoder(a);b=self.encoder(b)
        p1,h1,f1=self.emit(self.prepare(a,b,pos_a,pos_b,0))
        incoming=mx.zeros_like(h1) if erase_first else h1
        p2,h2,f2=self.emit(self.prepare(incoming,incoming,pos_pair,pos_pair,1))
        pointers=mx.stop_gradient(mx.argmax(mx.stack((p1,p2)),axis=-1))
        addresses=mx.stack((pos_b[pointers[0]],pos_pair[pointers[1]]))
        return dict(pointer_logits=mx.stack((p1,p2)),field_logits=mx.stack((f1,f2)),
                    latent=mx.stack((h1,h2)),pointers=pointers,addresses=addresses)

    def serial_same_queries(self,a,b,pos_a,pos_b,pos_pair):
        # Diagnostic serialization of the SAME query function, not an AR baseline.
        a=self.encoder(a);b=self.encoder(b);n=a.shape[1]
        outputs=[];latents=[];fields=[]
        for phase in range(2):
            source,memory=(a,b) if phase==0 else (latents[0],latents[0])
            qpos,mpos=(pos_a,pos_b) if phase==0 else (pos_pair,pos_pair)
            prepared=self.prepare(source,memory,qpos,mpos,phase)
            pp=[];hh=[];ff=[]
            for i in range(n):
                q,m,t,qp=prepared
                p,h,f=self.emit((q[:,i:i+1],m,t[:,i:i+1],qp[i:i+1]))
                pp.append(p);hh.append(h);ff.append(f)
            outputs.append(mx.concatenate(pp,1));latents.append(mx.concatenate(hh,1));fields.append(mx.concatenate(ff,1))
        ptr=mx.stop_gradient(mx.argmax(mx.stack(outputs),-1))
        return dict(pointer_logits=mx.stack(outputs),field_logits=mx.stack(fields),latent=mx.stack(latents),
                    pointers=ptr,addresses=mx.stack((pos_b[ptr[0]],pos_pair[ptr[1]])))


def loss(model,a,b,pa,pb,pp,targets,fields):
    out=model.forward(a,b,pa,pb,pp)
    logits=out['pointer_logits'];total=nn.losses.cross_entropy(logits.reshape(-1,logits.shape[-1]),targets.reshape(-1),reduction='mean')
    start=0
    for column,width in enumerate((KEYS,KEYS,VALUES,VALUES)):
        value=out['field_logits'][...,start:start+width]
        total+=nn.losses.cross_entropy(value.reshape(-1,width),fields[...,column].reshape(-1),reduction='mean')
        start+=width
    return total
