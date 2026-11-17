"""Offline whole-graph inputs and rule-derived labels; never called between NN steps."""
import hashlib
import numpy as np

KEYS=16
VALUES=4
FEATURES=2*KEYS+VALUES+2
# Shared template descriptions: input A/B or generated Pair/Pair, which field joins,
# two source bindings, one resulting Cell. These are not per-instance embeddings.
TEMPLATES=np.array([[1,0,0,0,1,0,1,0],[0,1,0,1,0,0,1,0]],np.float32)


def permutation(n,rng,family):
    order=rng.permutation(n);dest=np.arange(n)
    if family=='involution':
        start=0
        while start<n:
            if start+1<n and rng.random()<.8:
                a,b=order[start:start+2];dest[a]=b;dest[b]=a;start+=2
            else:start+=1
    elif family=='long_cycle':
        dest[order]=np.roll(order,-1)
    elif family=='arbitrary':dest=rng.permutation(n)
    elif family=='short_cycles':
        start=0
        while start<n:
            size=int(rng.integers(1,min(3,n-start)+1));group=order[start:start+size]
            dest[group]=np.roll(group,-1);start+=size
    elif family=='functional':
        dest=rng.integers(n,size=n)
        while len(set(dest.tolist()))==n:dest=rng.integers(n,size=n)
    else:raise ValueError(family)
    return dest


def generate(rows,length,count,seed,family='involution'):
    rng=np.random.default_rng(seed);n=rows*length
    if n>KEYS:raise ValueError('key vocabulary capacity')
    a=np.zeros((count,n,2),np.int32);b=np.zeros((count,n,3),np.int32)
    coords_a=np.array([(i//length,i%length) for i in range(n)],np.int32)
    coords_b=coords_a+np.array([0,length],np.int32)
    coords_pair=coords_a+np.array([0,2*length],np.int32)
    labels=[];field_labels=[];cycle_keys=[]
    for g in range(count):
        keys=rng.choice(KEYS,n,replace=False);dest=permutation(n,rng,family)
        a[g,:,0]=keys;a[g,:,1]=rng.integers(VALUES,size=n)
        physical_order=rng.permutation(n)
        b[g,:,0]=keys[physical_order];b[g,:,1]=keys[dest[physical_order]];b[g,:,2]=rng.integers(VALUES,size=n)
        # Labels from actual relation tables, not the generating permutation.
        match=np.array([np.flatnonzero(b[g,:,0]==key).item() for key in a[g,:,0]],np.int32)
        first=np.stack((a[g,:,0],b[g,match,1],a[g,:,1],b[g,match,2]),-1)
        successor=np.array([np.flatnonzero(first[:,0]==key).item() for key in first[:,1]],np.int32)
        second=np.stack((first[:,0],first[successor,1],first[:,2],first[successor,3]),-1)
        labels.append([match,successor]);field_labels.append([first,second])
        visited=set();cycles=[]
        for i in range(n):
            if i in visited:continue
            path=[];offset={};j=i
            while j not in visited and j not in offset:
                offset[j]=len(path);path.append(j);j=int(successor[j])
            if j in offset:cycles.append(len(path)-offset[j])
            visited.update(path)
        cycle_keys.append(tuple(sorted(cycles)))
    x_a=np.concatenate((np.eye(KEYS)[a[:,:,0]],np.zeros((count,n,KEYS)),np.eye(VALUES)[a[:,:,1]],np.broadcast_to([1,0],(count,n,2))),-1).astype(np.float32)
    x_b=np.concatenate((np.eye(KEYS)[b[:,:,0]],np.eye(KEYS)[b[:,:,1]],np.eye(VALUES)[b[:,:,2]],np.broadcast_to([0,1],(count,n,2))),-1).astype(np.float32)
    return dict(a=a,b=b,x_a=x_a,x_b=x_b,coords_a=coords_a,coords_b=coords_b,coords_pair=coords_pair,
                targets=np.array(labels,np.int32).transpose(1,0,2),fields=np.array(field_labels,np.int32).transpose(1,0,2,3),
                cycle_keys=cycle_keys,rows=rows,length=length,family=family)


def fingerprints(data):
    return [hashlib.sha256(data['a'][i].tobytes()+data['b'][i].tobytes()+data['coords_a'].tobytes()+data['coords_b'].tobytes()).hexdigest() for i in range(len(data['a']))]


def audit(data,pointers,fields,addresses):
    """Independent relational joins; all outputs must jointly cover each obligation."""
    a,b=data['a'],data['b'];graphs,n=a.shape[:2]
    whole=0;stage_ok=np.zeros(2,np.int64);pointer_ok=np.zeros(2,np.int64);values_ok=np.zeros(2,np.int64)
    missing=0;duplicates=0;reference_errors=0;cross=0;cross_correct=0;examples=[]
    for g in range(graphs):
        first=[];valid_first=[]
        for i in range(n):
            j=int(pointers[0,g,i]);valid=0<=j<n and a[g,i,0]==b[g,j,0]
            pointer_ok[0]+=valid
            truth=tuple(map(int,(a[g,i,0],b[g,j,1],a[g,i,1],b[g,j,2]))) if 0<=j<n else None
            value_ok=truth is not None and tuple(fields[0,g,i])==truth
            values_ok[0]+=value_ok
            coord=data['coords_b'][j] if 0<=j<n else None
            addr_ok=coord is not None and np.array_equal(addresses[0,g,i],coord)
            reference_errors+=not addr_ok
            valid_first.append(valid and value_ok and addr_ok);first.append(truth)
        actual_pairs={(i,int(pointers[0,g,i])) for i in range(n) if valid_first[i]}
        expected_pairs={(i,j) for i in range(n) for j in range(n) if a[g,i,0]==b[g,j,0]}
        one=all(valid_first) and actual_pairs==expected_pairs
        stage_ok[0]+=one
        second=[]
        for i in range(n):
            j=int(pointers[1,g,i])
            valid=0<=j<n and first[i] is not None and first[j] is not None and first[i][1]==first[j][0] and valid_first[i] and valid_first[j]
            pointer_ok[1]+=valid
            truth=(first[i][0],first[j][1],first[i][2],first[j][3]) if 0<=j<n and first[i] and first[j] else None
            value_ok=truth is not None and tuple(fields[1,g,i])==truth
            values_ok[1]+=value_ok
            coord=data['coords_pair'][j] if 0<=j<n else None
            addr_ok=coord is not None and np.array_equal(addresses[1,g,i],coord)
            reference_errors+=not addr_ok;second.append(valid and value_ok and addr_ok)
            true_j=int(data['targets'][1,g,i])
            if data['coords_pair'][i,0]!=data['coords_pair'][true_j,0]:
                cross+=1;cross_correct+=second[-1]
        two=all(second);stage_ok[1]+=two;whole+=one and two
        missing+=sum(not x for x in valid_first)+sum(not x for x in second)
        duplicates+=n-len(set(map(int,pointers[0,g])))
        if not (one and two) and len(examples)<3:
            examples.append(dict(a=a[g].tolist(),b=b[g].tolist(),predicted=pointers[:,g].tolist(),expected=data['targets'][:,g].tolist()))
    return dict(graphs=graphs,whole_graph_passed=int(whole),stage_graph_passed=stage_ok.tolist(),
                obligations=2*graphs*n,missing_or_invalid_obligations=int(missing),
                exact_pointer_count=pointer_ok.tolist(),decoded_value_count=values_ok.tolist(),
                repeated_first_stage_partner_count=int(duplicates),reference_errors=int(reference_errors),
                cross_row_successor_obligations=int(cross),cross_row_successor_correct=int(cross_correct),examples=examples)
