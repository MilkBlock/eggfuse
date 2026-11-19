"""Offline construction of provenance-sensitive requests for certified local unions."""
from hashlib import sha256
import numpy as np
if __package__:
    from .runtime import partition_record
else:
    from runtime import partition_record

STATES=('pre','post','nonmerge','external')
PROBES=('sentinel','local','origin','cross')
SIZES={'train':1024,'test':128}
MAKE_ROUTES=((0,0),(0,1),(0,2),(0,3),(1,1))
FINISH_ROUTES=((0,0),(0,1),(1,4),(0,3),(0,4))


def certificate(t):
    certs=t['certificates']
    if len(certs)!=1:raise ValueError('expected exactly one local union proof')
    cert=certs[0];p,q=cert['left_port'],cert['right_port'];public=sorted(t['public_ports'])
    if (len(public)!=3 or len(set(public))!=3 or p==q or p not in public or q not in public
        or cert['guard']!='producer_committed' or cert['visible_from_stage']!=1
        or cert['scope']!='template_local' or any(t['ports'][i]['sort']!=cert['sort'] for i in public)):
        raise ValueError('three coobservable same-sort ports with a guarded certificate required')
    return public,(p,q), next(i for i in public if i not in (p,q))


def seed(group,split,template):
    text=f'eggfuse.eclass.frontier.v1/{split}/{template}/{group}'
    return int.from_bytes(sha256(text.encode()).digest()[:8],'little')


def targets(template,a,b,req,a_port,phase,committed,external):
    classes,_,_=partition_record(template,a,a_port,phase,committed,external)
    one=np.zeros((8,8),np.int32);two=np.zeros_like(one);legal=np.zeros((8,len(req)),np.int32)
    count=0
    for i,row in enumerate(a):
        for j,frame in enumerate(b):
            if row[0]!=frame[0]:continue
            one[count]=[1,i,j,*row,int(frame[1])];count+=1
    out=0
    for pi,(live,i,j,*row) in enumerate(one):
        if not live:continue
        source=tuple(row[:2]);owner,port,raw,payload,tag=row
        for ri,(lookup_owner,lookup_port,required_owner,required_port,rtag) in enumerate(req):
            if (required_owner,required_port)!=source:continue
            if (lookup_owner,lookup_port) not in classes[source]:continue
            two[out]=[1,pi,ri,owner,port,rtag,payload,tag];out+=1;legal[pi,ri]=1
    return one,two,legal


def base_group(template,split,group):
    public,pair,other=certificate(template);blind=group%2==1
    rng=np.random.default_rng(seed(group,split,'blind-shared' if blind else template['id']))
    focus=group%2 if rng.integers(2)==0 else 1-group%2
    peer=1-focus
    # Free numeric handles are assigned in the PUBLIC PORT ORDER, never in the
    # [certificate-left,certificate-right,distractor] order. Slots are shuffled.
    handles=np.stack([rng.choice(8,3,replace=False) for _ in range(2)])
    raw_ids=rng.choice(8,6,replace=False).reshape(2,3)
    payload=int(rng.integers(8));tags=rng.integers(8,size=2)
    a=np.array([[o,handles[o,h],raw_ids[o,h],payload] for o in range(2) for h in range(3)],np.int32)
    a_port=np.tile(np.array(public,np.int32),2);order=rng.permutation(6);a=a[order];a_port=a_port[order]
    b=np.array([[o,tags[o]] for o in range(2)],np.int32)[rng.permutation(2)]
    if blind:
        # All ten templates get literally identical public arrays in this stratum.
        # Cycle through every unordered physical pair, independently of its proof.
        u,v=((0,1),(0,2),(1,2))[(group//2)%3]
        if rng.integers(2):u,v=v,u
        w=next(k for k in range(3) if k not in (u,v))
        p,q,r=u,v,w
    else:
        p,q=map(public.index,pair);r=public.index(other)
        if rng.integers(2):p,q=q,p
    # One scoped external union edge per external graph. The blocked local
    # receipt case is distinct from the neutral port, which stays unrelated
    # even after a producer succeeds. External signs vary across base groups.
    left,right=divmod(group%9,3)
    edge=np.array([1,focus,handles[focus,left],peer,handles[peer,right]],np.int32)
    edge_ports=np.array([public[left],public[right]],np.int32)
    index=group//2
    local_origin=q if index%2==0 else r
    # Probe either the external endpoints' local peers or the complementary
    # class. The latter can be a true secondary congruence on some templates.
    # Probe construction uses no CPU equality matrix, even on these events.
    if left in (p,q) and right in (p,q) and index%3!=2:
        cross_read,cross_origin=r,r
    elif left==r and right==r:
        cross_read,cross_origin=p,q
    else:
        cross_read=q if left==p else (p if left==q else r)
        cross_origin=q if right==p else (p if right==q else r)
        if index%4==3:cross_origin=r if cross_origin in (p,q) else p
    req_order=rng.permutation(4);req_tags=rng.choice(8,4,replace=False)
    records=[]
    for state,mode in enumerate(STATES):
        phase=np.full(2,int(mode!='pre'),np.int32)
        committed=phase.copy()
        if mode=='nonmerge':committed[focus]=0
        external=edge.copy() if mode=='external' else np.zeros(5,np.int32)
        external_ports=edge_ports.copy() if mode=='external' else np.zeros(2,np.int32)
        for variant in (0,1):
            # Role labels tag offline diagnostics. Request order is independent.
            refs=[(peer,r,peer,r),(focus,p,focus,local_origin),
                  (focus,p,focus,p if variant==0 else q),(focus,cross_read,peer,cross_origin)]
            req=np.array([[o,handles[o,x],t,handles[t,y],z] for z,(o,x,t,y) in zip(req_tags,refs)],np.int32)[req_order]
            req_ports=np.array([[public[x],public[y]] for _,x,_,y in refs],np.int32)[req_order]
            one,two,legal=targets(template,a,b,req,a_port,phase,committed,external)
            records.append(dict(a=a,b=b,requests=req,a_port=a_port,request_ports=req_ports,
                phase=phase,committed=committed,external=external,external_ports=external_ports,
                target1=one,target2=two,legal_parents=legal,request_legal=legal.any(0).astype(np.int32),
                state=np.int32(state),variant=np.int32(variant),group_id=np.int32(group),
                focal_owner=np.int32(focus),probe_kind=req_order.astype(np.int32),blind=np.int32(blind)))
    return records


def dataset(split,template,n=None):
    if split not in SIZES:raise ValueError('split must be train or test')
    if split=='train' and template['split']!='train':raise ValueError('held-out templates cannot enter training')
    size=SIZES[split] if n is None else int(n)
    if size<8 or size%8:raise ValueError('a complete state/origin group comprises eight graphs')
    records=[row for group in range(size//8) for row in base_group(template,split,group)]
    values={k:np.stack([r[k] for r in records]) for k in records[0]}
    values.update(template=template,template_id=template['id'],split=split)
    return values
