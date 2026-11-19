"""Synthetic typed candidate frontiers for real, two-step Bake interface contracts."""
from functools import lru_cache
from hashlib import sha256
import json
import numpy as np

CAPACITY = 8
RECORDS = 4
SIZES = {'train':1024, 'iid':64, 'collision':64}


def operand(point, left, right):
    side, column = point
    if side == 0:
        return int(left[column])
    if side == 1:
        return int(right[column])
    if side == 2:
        return int(column)
    raise ValueError(f'unsupported operand side {side}')


def execute(stage, left, right):
    """Scalar source semantics on an individual candidate pair."""
    for lhs, rhs in stage['checks']:
        if operand(lhs,left,right) != operand(rhs,left,right):
            return None
    return tuple(operand(point,left,right) for point in stage['outputs'])


def reference(stages, a, b, requests):
    made = {}
    result = {}
    for i, left in enumerate(a):
        for j, right in enumerate(b):
            row = execute(stages[0], left, right)
            if row is not None:
                made[i,j] = row
                for ri, request in enumerate(requests):
                    out = execute(stages[1], row, request)
                    if out is not None:
                        result[i,j,ri] = out
    return made,result


def targets(stages, made, result):
    if len(made)>CAPACITY or len(result)>CAPACITY:
        raise ValueError('complete source witness set exceeds decoder capacity')
    first, second = [np.zeros((CAPACITY,3+len(s['outputs'])),np.int32) for s in stages]
    slots = {binding:slot for slot,binding in enumerate(made)}
    for (i,j),row in made.items():
        first[slots[i,j]] = [1,i,j,*row]
    for slot, ((i,j,r),row) in enumerate(result.items()):
        second[slot] = [1,slots[i,j],r,*row]
    return first,second


class Wiring:
    """Construct sampling constraints for a few desired witnesses, never the labels."""
    def __init__(self):
        self.parent = []
        self.value = {}

    def variables(self, sorts):
        refs=[]
        for sort in sorts:
            ref=len(self.parent);self.parent.append(ref);refs.append(ref)
            if sort=='Unit':self.value[ref]=0
        return refs

    def literal(self,value):
        ref=len(self.parent);self.parent.append(ref);self.value[ref]=value
        return ref

    def root(self,i):
        while self.parent[i]!=i:
            i=self.parent[i]
        return i

    def unify(self,i,j):
        left,right = self.root(i),self.root(j)
        if left==right:return
        if left in self.value and right in self.value and self.value[left]!=self.value[right]:
            raise ValueError('contradictory literal or Unit equality in source witness')
        self.parent[right]=left
        if right in self.value:self.value[left]=self.value.pop(right)

    def attach(self,stage,left,right):
        def ref(point):
            side,col=point
            return self.literal(col) if side==2 else (left,right)[side][col]
        for lhs,rhs in stage['checks']:
            self.unify(ref(lhs),ref(rhs))
        return [ref(p) for p in stage['outputs']]


def recipe_sample(stages, n_made, req_parents, shared_fact, distinguishing_index):
    w=Wiring();make,finish=stages
    a=[w.variables(make['left_sorts']) for _ in range(4)]
    b=[w.variables(make['right_sorts']) for _ in range(4)]
    r=[w.variables(finish['right_sorts']) for _ in range(5)]
    # Some different producer-frame events access the same functional fact.
    # The RHS key of the fact table will be unique across physical B rows.
    made=[]
    for i in range(n_made):
        j=0 if shared_fact and i==n_made-1 else i
        made.append(w.attach(make,a[i],b[j]))
    for ri,parent in enumerate(req_parents):
        w.attach(finish,made[parent],r[ri])
    if distinguishing_index is not None:
        # A counterfactual substitutes the other real parent in the same Request
        # slot. Other rows, all unconstrained request fields, and the source graph
        # are held fixed. Both parents must satisfy the actual consumer guards.
        w.attach(finish,made[1],r[4]);bits=(w.root(made[0][distinguishing_index]),w.root(made[1][distinguishing_index]))
        if any(x in w.value for x in bits) or bits[0]==bits[1]:
            return None
        for col in range(len(made[0])):
            if w.root(made[0][col]) != bits[0]:
                w.unify(made[0][col],made[1][col])
        for col in range(len(r[0])):
            if w.root(r[0][col])!=bits[0] and w.root(r[4][col])!=bits[1]:
                w.unify(r[0][col],r[4][col])
        if w.root(bits[0]) == w.root(bits[1]):return None
    roots=sorted({w.root(i) for i in range(len(w.parent))});rename={old:i for i,old in enumerate(roots)}
    def mapped(rows):return np.asarray([[rename[w.root(i)] for i in row] for row in rows],dtype=np.int32)
    return (len(roots),[(rename[i],value) for i,value in w.value.items()],mapped(a),mapped(b),mapped(r))


@lru_cache(maxsize=64)
def compiled_samplers(encoded):
    stages=json.loads(encoded);make,finish=stages
    if make['outputs'] != [[1,i] for i in range(make['right_width'])] or make['right_width']<2:
        raise ValueError('supported producer must publish the entire ordered functional fact')
    # A distinguishable parent perturbation must affect a genuine consumer join
    # and at least one physical fact key column. Changing a functional result
    # alone for an identical fact key would fabricate an impossible fact store.
    keys={one[1] for pair in finish['checks'] for one,other in (pair,pair[::-1]) if one[0]==0 and other[0]==1}
    choices=sorted(keys & set(range(make['right_width']-1)))
    collision=[];plain=[]
    for col in choices:
        for n_made,parents in [(2,(0,)),(3,(0,2)),(4,(0,2,3))]:
            sam=recipe_sample(stages,n_made,parents,False,col)
            if sam:collision.append(sam)
    if not collision:raise ValueError('no distinguishable parent intersection for this template')
    for n,parents,shared in [(0,(),False),(1,(0,),False),(2,(1,),False),(3,(1,2),False),
                              (2,(0,1),False),(3,(0,),True),(4,(0,1,2),True),(4,(0,1,2,3),False)]:
        plain.append(recipe_sample(stages,n,parents,shared,None))
    return plain,collision


def draw(rng,sampler,stages,is_twin):
    size,fixed,ia,ib,ir=sampler
    vals=rng.integers(0,8,size,dtype=np.int32)
    for idx,value in fixed:vals[idx]=value
    a,b,r=vals[ia],vals[ib],vals[ir]
    # A physical function table has one row per complete key, including constant
    # inputs. A/Request are separate input events and may legally share a payload.
    if len({tuple(x[:-1]) for x in b})!=4:return None
    ai,bi,ri=(rng.permutation(4) for _ in range(3));a=a[ai];b=b[bi]
    if is_twin:
        left,right = [(int(np.flatnonzero(ai==i)[0]),int(np.flatnonzero(bi==i)[0])) for i in (0,1)]
        req_slot=int(np.flatnonzero(ri==0)[0]);alt=r[:4].copy();alt[0]=r[4];cases=[r[:4][ri],alt[ri]]
    else:cases=[r[:4][ri]]
    records=[]
    for side,req in enumerate(cases):
        made,result = reference(stages,a,b,req)
        if max(len(made),len(result))>CAPACITY:return None
        probe=np.full(5,-1,np.int32)
        if is_twin:
            wanted,other=(left,right) if side==0 else (right,left)
            if (*wanted,req_slot) not in result or (*other,req_slot) in result:return None
            if not any(x==y for x,y in zip(made[wanted],made[other])):return None
            probe[:]=[*wanted,*other,req_slot]
        one,two=targets(stages,made,result)
        records.append((a,b,req,one,two,probe))
    return records


def dataset(split, family, n=None):
    """Return a reproducible single-template panel. Collision entries are adjacent twins."""
    if split not in SIZES:raise ValueError(f'unknown split: {split}')
    if split=='train' and family.get('split')=='heldout':raise ValueError('held-out template cannot train')
    n=SIZES[split] if n is None else int(n)
    if n<1 or (split=='collision' and n%2):raise ValueError('collision panel requires positive even size')
    stages=family['stages']; encoded=json.dumps(stages,sort_keys=True,separators=(',',':'))
    plain,collision=compiled_samplers(encoded)
    seed=int.from_bytes(sha256(f"eggfuse.port.frontier.v1/{family['id']}/{split}".encode()).digest()[:8],'little')
    rng=np.random.default_rng(seed);data=[];attempt_limit=max(5000,n*128);attempts=0;seen=set()
    while len(data)<n:
        attempts+=1
        if attempts>attempt_limit:raise ValueError(f"could not sample the complete panel {family['id']}/{split} ({len(data)}/{n})")
        twin=split=='collision' or (len(data)%8==0 and len(data)+2<=n)
        bank=collision if twin else plain
        records=draw(rng,bank[int(rng.integers(len(bank)))],stages,twin)
        if records is None:continue
        signatures=[b''.join(x.tobytes() for x in record[:3]) for record in records]
        if len(set(signatures))!=len(records) or any(k in seen for k in signatures):continue
        seen.update(signatures);data.extend(records)
    result={k:np.stack(v) for k,v in zip(('a','b','requests','target1','target2','probe'),zip(*data))}
    result.update(stages=stages, template_id=family['id'], family_id=family['family_id'],split=split,seed=seed)
    result['request_slots']=result['target2'][...,2]
    return result
