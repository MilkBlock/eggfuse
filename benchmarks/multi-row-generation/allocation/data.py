"""Offline finite equality-join data and independent whole-set audit."""
from itertools import combinations_with_replacement
from collections import Counter
import hashlib
import numpy as np
K=8;V=4;N=4;Q=8;FEATURES=K+V+2


def shape(a,b):
    ca=Counter(map(int,a[:,0]));cb=Counter(map(int,b[:,0]))
    return tuple(sorted((ca[k],cb[k]) for k in set(ca)|set(cb)))


def fingerprint(a,b):return hashlib.sha256(a.tobytes()+b.tobytes()).hexdigest()


def truth(a,b):return [(i,j,int(a[i,0]),int(a[i,1]),int(b[j,1])) for i in range(N) for j in range(N) if a[i,0]==b[j,0]]


def features(a,b):
    def enc(x,t):return np.concatenate((np.eye(K,dtype=np.float32)[x[...,0]],np.eye(V,dtype=np.float32)[x[...,1]],np.broadcast_to(t,x.shape[:-1]+(2,))),-1).astype(np.float32)
    return np.concatenate((enc(a,[1,0]),enc(b,[0,1])),1)


def generate(count,seed,held=False,forbidden=()):
    # Six temporary key groups suffice to span zero through eight obligations.
    multisets=list(combinations_with_replacement(range(6),N));pairs={}
    for aa in multisets:
        ca=Counter(aa)
        if max(ca.values())!=(3 if held else 2) and (held or max(ca.values())>2):continue
        for bb in multisets:
            cb=Counter(bb)
            if max(cb.values())>2:continue
            m=sum(ca[k]*cb[k] for k in ca)
            if m>Q or (held and m==0):continue
            pairs.setdefault(m,[]).append((aa,bb))
    counts=sorted(pairs);rng=np.random.default_rng(seed);a=[];b=[];seen=set(forbidden)
    while len(a)<count:
        bank=pairs[counts[len(a)%len(counts)]];aa,bb=bank[int(rng.integers(len(bank)))];keys=rng.permutation(K)
        x=np.stack((keys[np.array(aa)][rng.permutation(N)],rng.integers(V,size=N)),-1).astype(np.int32)
        y=np.stack((keys[np.array(bb)][rng.permutation(N)],rng.integers(V,size=N)),-1).astype(np.int32)
        fp=fingerprint(x,y)
        if fp in seen:continue
        seen.add(fp);a.append(x);b.append(y)
    a=np.array(a);b=np.array(b);targets=np.zeros((count,Q,6),np.int32)
    for g in range(count):
        for t,record in enumerate(truth(a[g],b[g])):targets[g,t]=[1,*record]
    return dict(a=a,b=b,x=features(a,b),targets=targets)


def coordinates(rows,length):
    assert rows*length==Q
    source=np.array([(i//length,i%length) for i in range(Q)],np.int32)
    return source,source+np.array([0,length],np.int32)


def audit(a,b,out,source_pos):
    counts=Counter();by_count={};examples=[]
    for g in range(len(a)):
        expected={(i,j):(k,x,y) for i,j,k,x,y in truth(a[g],b[g])};valid=[];bad=0
        for s in range(Q):
            if not out['active'][g,s]:continue
            i,j=map(int,out['pointers'][g,s]);pair=(i,j);fields=tuple(map(int,out['fields'][g,s]));legal=pair in expected
            field_ok=legal and fields==expected[pair]
            address_ok=0<=i<N and 0<=j<N and np.array_equal(out['addresses'][g,s],source_pos[[i,N+j]])
            counts['illegal_bindings']+=not legal;counts['field_errors']+=legal and not field_ok;counts['address_errors']+=not address_ok
            if legal and field_ok and address_ok:valid.append(pair)
            else:bad+=1
        duplicate=len(valid)-len(set(valid));missing=len(set(expected)-set(valid));correct=not(bad or duplicate or missing)
        counts['complete_graphs']+=correct;counts['valid_unique']+=len(set(valid));counts['duplicates']+=duplicate;counts['missing']+=missing
        counts['obligations']+=len(expected);counts['count_error_graphs']+=int(out['active'][g].sum())!=len(expected)
        counts['active_outputs']+=int(out['active'][g].sum())
        for i,j in set(valid):counts['cross_row_valid']+=source_pos[i,0]!=source_pos[N+j,0]
        stat=by_count.setdefault(str(len(expected)),dict(graphs=0,complete=0));stat['graphs']+=1;stat['complete']+=int(correct)
        if not correct and len(examples)<3:examples.append(dict(a=a[g].tolist(),b=b[g].tolist(),expected=list(expected),active=out['active'][g].tolist(),pointers=out['pointers'][g].tolist()))
    return dict(graphs=len(a),**{k:int(v) for k,v in counts.items()},by_cardinality=by_count,examples=examples)
