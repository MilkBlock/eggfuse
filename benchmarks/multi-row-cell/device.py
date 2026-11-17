"""GPU-only compressed Cell views and supplied-proposal ownership transitions.

Rows contain multiple instance tokens. Instance payloads contain boundary refs,
not member instructions or node values. This is a deterministic execution
foundation; no neural proposer, union solver, or complete eggcc engine is claimed.
"""
import numpy as np
import mlx.core as mx
from catalog import ABSENT

FREE,LIVE,FORWARD=0,1,2
OK,BAD_ADDRESS,STALE,UNPUBLISHED,HOP_BUDGET=0,1,2,3,4

def replace_at(array,index,value):
    mask=(mx.arange(len(array))==index).reshape((len(array),)+(1,)*(array.ndim-1))
    return mx.where(mask,value,array)

def refs_at(row,pos,port,gen):return mx.stack(mx.broadcast_arrays(row,pos,port,gen),-1).astype(mx.int32)

class Device:
    def __init__(self,catalog,rows,length,arena_capacity=None,max_hops=16):
        if not mx.metal.is_available():raise RuntimeError('Metal required')
        mx.set_default_device(mx.gpu)
        if rows<1 or length<1 or max_hops<1 or (arena_capacity is not None and arena_capacity<1):raise ValueError('positive layout and resolver budget required')
        self.rows=rows;self.length=length;self.slots=rows*length
        self.capacity=arena_capacity or self.slots;self.hops=max_hops
        arrays=catalog.arrays();self.lib={k:mx.array(v) for k,v in arrays.items()};self.parameter_counts=arrays['parameter_count']
        self.ports=arrays['kind'].shape[1];self.params=arrays['boundary_source'].shape[1]
        self.arity=arrays['args'].shape[-1];self.plan_count=len(catalog.compositions)

    def initialize(self,instances):
        """Initial input upload only. instances=(row,pos,template,bindings,locality)."""
        n=self.slots;c=self.capacity;b=self.params
        state=dict(kind=np.zeros(n,np.int32),template=np.full(n,-1,np.int32),generation=np.zeros(n,np.int32),
            locality=np.full(n,-1,np.int32),payload=np.full(n,-1,np.int32),
            destination=np.full((n,3),-1,np.int32),projection=np.full(n,-1,np.int32),
            arena=np.tile(np.array(ABSENT,np.int32),(c,b,1)),arena_owner=np.full(c,-1,np.int32),
            done=np.zeros(c,np.uint32),run=np.array(0,np.int32))
        if len(instances)>c:raise ValueError('arena capacity')
        for p,(row,pos,tpl,bindings,locality) in enumerate(instances):
            if not (0<=row<self.rows and 0<=pos<self.length):raise ValueError('instance coordinate')
            i=row*self.length+pos
            if state['kind'][i]:raise ValueError('duplicate coordinate')
            if not 0<=tpl<len(self.parameter_counts) or len(bindings)!=self.parameter_counts[tpl]:raise ValueError('binding arity')
            state['kind'][i]=LIVE;state['template'][i]=tpl;state['generation'][i]=1
            state['locality'][i]=locality;state['payload'][i]=p;state['arena_owner'][p]=i
            state['arena'][p,:len(bindings)]=bindings
        return {k:mx.array(v) for k,v in state.items()}

    def _index(self,q):
        valid=(q[...,0]>=0)&(q[...,0]<self.rows)&(q[...,1]>=0)&(q[...,1]<self.length)
        return mx.clip(q[...,0]*self.length+q[...,1],0,self.slots-1),valid

    def resolve(self,state,query,visible=True):
        shape=query.shape[:-1];q=query.reshape(-1,4);n=len(q)
        done=mx.zeros((n,),mx.bool_);error=mx.zeros((n,),mx.int32)
        for _ in range(self.hops):
            active=~done
            atom=(q[:,0]==-1)&(q[:,2]==0)&(q[:,3]==0)
            idx,in_bounds=self._index(q);tpl=mx.clip(state['template'][idx],0,len(self.lib['kind'])-1)
            port=mx.clip(q[:,2],0,self.ports-1)
            port_ok=(q[:,2]>=0)&(q[:,2]<self.lib['port_count'][tpl])
            generation_ok=q[:,3]==state['generation'][idx]
            kind=state['kind'][idx];p=mx.clip(state['payload'][idx],0,self.capacity-1)
            owned=(state['payload'][idx]>=0)&(state['payload'][idx]<self.capacity)&(state['arena_owner'][p]==idx)
            live=(kind==LIVE)&owned
            forwarding=kind==FORWARD
            address_ok=in_bounds&port_ok&(live|forwarding)&(state['template'][idx]>=0)&(state['template'][idx]<len(self.lib['kind']))&(state['generation'][idx]>0)
            bad=active&~atom&~address_ok
            stale=active&~atom&address_ok&~generation_ok
            valid=active&~atom&address_ok&generation_ok
            pk=self.lib['kind'][tpl,port];field=self.lib['field'][tpl,port]
            binding=valid&live&(pk==1)
            constructor=valid&live&(pk==2)
            published=((state['done'][p]&(mx.array(1,mx.uint32)<<port.astype(mx.uint32)))!=0)&(self.lib['run'][tpl,port]<=state['run'])
            hidden=constructor&~published if visible else mx.zeros_like(constructor)
            proj=state['projection'][idx];mapped=self.lib['projection'][mx.clip(proj,0,len(self.lib['projection'])-1),port]
            dest=state['destination'][idx]
            next_forward=refs_at(dest[:,0],dest[:,1],mapped,dest[:,2])
            forwarding_bad=valid&forwarding&((proj<0)|(mapped<0))
            bound=state['arena'][p,mx.clip(field,0,self.params-1)]
            q=mx.where(binding[:,None],bound,q)
            q=mx.where((valid&forwarding&~forwarding_bad)[:,None],next_forward,q)
            error=mx.where(bad|forwarding_bad,BAD_ADDRESS,mx.where(stale,STALE,mx.where(hidden,UNPUBLISHED,error)))
            done |= (active&atom)|bad|stale|forwarding_bad|constructor
        error=mx.where(~done,HOP_BUDGET,error)
        return dict(reference=q.reshape(shape+(4,)),valid=(done&(error==OK)).reshape(shape),error=error.reshape(shape))

    def view(self,state,query):
        resolved=self.resolve(state,query);q=resolved['reference'].reshape(-1,4)
        idx,_=self._index(q);tpl=mx.clip(state['template'][idx],0,len(self.lib['kind'])-1);port=mx.clip(q[:,2],0,self.ports-1)
        local_args=self.lib['args'][tpl,port]
        args=refs_at(q[:,0,None],q[:,1,None],local_args,q[:,3,None])
        atom=q[:,0]==-1
        arity=mx.sum(local_args>=0,axis=-1).astype(mx.int32)
        arity=mx.where(atom,0,arity)
        shape=query.shape[:-1]
        return dict(**resolved,query=query,opcode=mx.where(atom,-1,self.lib['field'][tpl,port]).reshape(shape),
                    arity=arity.reshape(shape),arguments=args.reshape(shape+(self.arity,4)),value=q[:,1].reshape(shape))

    def publish(self,state,run,rounds=4):
        """Bounded device frontier: activate pure constructor views with visible args.

        Returns the count of still-unexecuted source operations, never calls an
        incomplete frontier saturated. No standalone member record is created.
        """
        s=dict(state)
        indices=mx.arange(self.slots);row=indices//self.length;pos=indices%self.length
        ports=mx.arange(self.ports);tpl=mx.clip(s['template'],0,len(self.lib['kind'])-1)
        p=mx.clip(s['payload'],0,self.capacity-1)
        live=(s['kind']==LIVE)&(s['payload']>=0)&(s['payload']<self.capacity)&(s['arena_owner'][p]==indices)&(s['template']>=0)&(s['template']<len(self.lib['kind']))
        is_ctor=self.lib['kind'][tpl]==2
        port_bits=mx.array(1,mx.uint32)<<ports.astype(mx.uint32)
        old_pending=mx.sum(live[:,None]&is_ctor&(self.lib['run'][tpl]<=state['run'])&((state['done'][p,None]&port_bits[None,:])==0))
        schedule_ok=(mx.array(run,mx.int32)==state['run'])|((mx.array(run,mx.int32)==state['run']+1)&(old_pending==0))
        s['run']=mx.where(schedule_ok,mx.array(run,mx.int32),state['run'])
        eligible=live[:,None]&is_ctor&(self.lib['run'][tpl]<=s['run'])
        for _ in range(rounds):
            local_args=self.lib['args'][tpl]
            q=refs_at(row[:,None,None],pos[:,None,None],local_args,s['generation'][:,None,None])
            resolved=self.resolve(s,q)
            ready=mx.all((local_args<0)|resolved['valid'],axis=-1)
            missing=(s['done'][p,None]&port_bits[None,:])==0
            new=eligible&ready&missing&schedule_ok
            bits=mx.sum(mx.where(new,port_bits[None,:],0),axis=-1).astype(mx.uint32)
            s['done']=s['done'].at[p].add(bits)
        missing=(s['done'][p,None]&port_bits[None,:])==0
        pending=mx.sum(eligible&missing)
        return s,dict(schedule_ok=schedule_ok,pending=pending)

    def transfer(self,state,proposal):
        """Validate one supplied composition and atomically re-use its left payload.

        proposal: plan, left(row,pos,gen), right(row,pos,gen), target(row,pos,oldgen), locality.
        Every branch is a GPU mask. The caller never supplies a computed binding or map.
        """
        plan=proposal[0];l=proposal[1:4];r=proposal[4:7];d=proposal[7:10];locality=proposal[10]
        li,lv=self._index(refs_at(l[0],l[1],mx.array(0),l[2]))
        ri,rv=self._index(refs_at(r[0],r[1],mx.array(0),r[2]))
        di,dv=self._index(refs_at(d[0],d[1],mx.array(0),d[2]))
        pi=mx.clip(plan,0,max(0,self.plan_count-1));templates=self.lib['plan'][pi]
        lp=mx.clip(state['payload'][li],0,self.capacity-1);rp=mx.clip(state['payload'][ri],0,self.capacity-1)
        checks=[(plan>=0)&(plan<self.plan_count),lv&rv&dv&(l[2]>0)&(r[2]>0)&(d[2]>=0)&(d[2]<2147483647)&(locality>=0),(li!=ri)&(li!=di)&(ri!=di),
            (state['kind'][li]==LIVE)&(state['kind'][ri]==LIVE)&(state['kind'][di]==FREE),
            (state['generation'][li]==l[2])&(state['generation'][ri]==r[2])&(state['generation'][di]==d[2]),
            (state['template'][li]==templates[0])&(state['template'][ri]==templates[1]),
            (state['payload'][li]>=0)&(state['payload'][li]<self.capacity)&(state['payload'][ri]>=0)&(state['payload'][ri]<self.capacity)&(lp!=rp),
            (state['arena_owner'][lp]==li)&(state['arena_owner'][rp]==ri)]
        wires=self.lib['wires'][pi];used=wires[:,0]>=0
        actual=state['arena'][rp,mx.clip(wires[:,0],0,self.params-1)]
        expected=refs_at(l[0],l[1],wires[:,1],l[2])
        av=self.resolve(state,actual,visible=False);ev=self.resolve(state,expected,visible=False)
        wired=mx.all(~used|(av['valid']&ev['valid']&mx.all(av['reference']==ev['reference'],axis=-1)))
        checks.append(wired)
        passed=mx.stack(checks);accepted=mx.all(passed)
        src=self.lib['boundary_source'][pi];bound_index=mx.clip(src[:,1],0,self.params-1)
        source_payload=mx.where(src[:,0]==0,lp,rp)
        bindings=state['arena'][source_payload,bound_index]
        bindings=mx.where((src[:,0]>=0)[:,None],bindings,mx.array(ABSENT,mx.int32))
        oldports=mx.arange(self.ports);oldbits=mx.array(1,mx.uint32)<<oldports.astype(mx.uint32)
        lm=self.lib['projection'][2*pi];rm=self.lib['projection'][mx.minimum(2*pi+1,len(self.lib['projection'])-1)]
        def project_done(payload,mapping):
            live=((state['done'][payload]&oldbits)!=0)&(mapping>=0)
            return mx.sum(mx.where(live,mx.array(1,mx.uint32)<<mx.clip(mapping,0,31).astype(mx.uint32),0)).astype(mx.uint32)
        done=project_done(lp,lm)|project_done(rp,rm)
        out=dict(state)
        def set_at(key,index,value):out[key]=replace_at(out[key],index,mx.where(accepted,value,out[key][index]))
        newgen=state['generation'][di]+1
        set_at('arena',lp,bindings);set_at('done',lp,done);set_at('arena_owner',lp,di)
        set_at('arena',rp,mx.broadcast_to(mx.array(ABSENT,mx.int32),(self.params,4)))
        set_at('done',rp,mx.array(0,mx.uint32));set_at('arena_owner',rp,mx.array(-1,mx.int32))
        for key,value in [('kind',LIVE),('template',templates[2]),('generation',newgen),('locality',locality),('payload',lp)]:set_at(key,di,mx.array(value,mx.int32))
        for idx,projection in [(li,2*pi),(ri,2*pi+1)]:
            set_at('kind',idx,mx.array(FORWARD,mx.int32));set_at('payload',idx,mx.array(-1,mx.int32))
            set_at('destination',idx,mx.stack((d[0],d[1],newgen)));set_at('projection',idx,projection)
        return out,dict(accepted=accepted,checks=passed,released_payload=mx.where(accepted,rp,-1))

    def transfer_batch(self,state,proposals):
        # The batch order is source effect order. Conflicting later claims reject.
        s=state;accepted=[];checks=[]
        for i in range(len(proposals)):
            s,receipt=self.transfer(s,proposals[i]);accepted.append(receipt['accepted']);checks.append(receipt['checks'])
        return s,dict(accepted=mx.stack(accepted),checks=mx.stack(checks))

    def address_bank(self,state):
        i=mx.arange(self.slots)[:,None];ports=mx.arange(self.ports)[None,:]
        return refs_at(i//self.length,i%self.length,ports,state['generation'][:,None]).reshape(-1,4)

    def read_encoded(self,state,keys,declared_references):
        """Rotary key chooses a joint address; integer reference binds its certificate.

        An inconsistent key/descriptor rejects. It NEVER substitutes the claimed
        address after a failed retrieval. This is not a learned key generator.
        """
        from rotary import select
        bank=self.address_bank(state)
        selected,nonempty=select(keys,bank,mx.ones((len(bank),),mx.bool_))
        match=nonempty&mx.all(selected==declared_references,axis=-1)
        out=self.view(state,selected)
        out['valid']=out['valid']&match
        out['error']=mx.where(match,out['error'],BAD_ADDRESS)
        out['address_match']=match
        return out

    def all_queries(self):
        i=mx.arange(self.slots)[:,None];p=mx.arange(self.ports)[None,:]
        return refs_at(i//self.length,i%self.length,p,mx.array(1))
