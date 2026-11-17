"""Trusted finite vocabulary and INPUT plans. No source truth supplied at inference."""
from itertools import combinations, permutations, product
import hashlib
import json
import numpy as np

DIM = 128
OLD, NEW, EMPTY = 8, 8, 9
PAIRS = list(combinations(range(OLD), 2))
# Each row: opcode (F=0 unary; H=1 ordered binary), argument 1, argument 2.
# Constructor outputs have roles 4..7; all four leaf roles exist initially.
SHAPES = [
    [(0,0,9),(0,1,9),(1,2,3),(1,3,2)],
    [(0,0,9),(0,1,9),(0,4,9),(0,5,9)],
    [(0,0,9),(0,1,9),(1,4,2),(1,5,2)],
    [(1,0,2),(1,1,2),(0,4,9),(0,5,9)],
    [(0,0,9),(0,1,9),(1,4,5),(0,6,9)],
    [(1,0,1),(0,4,9),(1,2,4),(1,5,6)],
    [(0,0,9),(1,4,1),(0,5,9),(1,6,2)],
    [(1,0,1),(1,2,3),(1,4,5),(1,0,5)],
    # Complete operator/edge patterns below never occur in training.
    [(0,0,9),(0,1,9),(1,4,4),(1,5,5)],
    [(1,0,1),(1,2,3),(0,4,9),(1,6,5)],
]
SHAPE_NAMES = ['mixed_forest','parallel_unary','parallel_binary_tails','parallel_unary_tails',
               'diamond','fanout','ladder','binary_join','held_double_arguments','held_delayed_join']
UNIONS = list(combinations(range(4),2)) + list(combinations(range(4,8),2))
HELD_UNIONS = [(1,3),(4,6)]

def layout_for(commands):
    """Offline layout policy: compose two adjacent swaps, then insert G at port 4."""
    out = list(range(8))
    for i in commands: out[i], out[i+1] = out[i+1], out[i]
    out.insert(4,8)
    return out

# Deduplicate by full resulting permutation, including commuting swaps and identity.
_map_commands = {}
for pair in product(range(7),repeat=2):
    _map_commands.setdefault(tuple(layout_for(pair)),pair)
MAPS = list(_map_commands.values())
HELD_MAPS = [MAPS.index(p) for p in [(1,2),(2,1),(4,5),(5,4)]]
TRAIN_SHAPES, HELD_SHAPES = list(range(8)), [8,9]
TRAIN_UNIONS = [i for i,p in enumerate(UNIONS) if p not in HELD_UNIONS]
TEST_UNIONS = [UNIONS.index(p) for p in HELD_UNIONS]
TRAIN_MAPS = [i for i in range(len(MAPS)) if i not in HELD_MAPS]
GROUPS = dict(
    seen=(TRAIN_SHAPES,TRAIN_UNIONS,TRAIN_MAPS),
    shape=(HELD_SHAPES,TRAIN_UNIONS,TRAIN_MAPS),
    union=(TRAIN_SHAPES,TEST_UNIONS,TRAIN_MAPS),
    mapping=(TRAIN_SHAPES,TRAIN_UNIONS,HELD_MAPS),
    joint=(HELD_SHAPES,TEST_UNIONS,HELD_MAPS),
)
# Case columns: shape, union pair, mapping command pair, enabled, query-left,
# query-right, four-bit opaque Cell annotation. IDs are metadata only, not features.
SPECS = dict(ops=(4,2), args=(4,2,10), layout=(9,10), alias=(8,10), eq=(28,),
             owner=(1,3), proof=(1,5), premises=(3,5), union_witness=(2,10),
             gate=(2,10), commands=(2,7), payload=(4,), pending=(2,), retired=(1,))
BOOL = {'eq','payload','pending','retired'}
OFFSETS, WIDTH = {}, 0
for k, shape in SPECS.items():
    n=int(np.prod(shape)); OFFSETS[k]=(WIDTH,WIDTH+n); WIDTH+=n
INPUT_WIDTH = 8+80+16+1+16+14+4

def shape_key(shape):
    """Alpha-invariant rooted term multiset, retaining ordered args and sharing."""
    keys=[]
    for perm in permutations(range(4)):
        terms=[f'x{i}' for i in perm]
        for op,a,b in shape:
            terms.append(f'F({terms[a]})' if op==0 else f'H({terms[a]},{terms[b]})')
        keys.append(tuple(sorted(terms[4:])))
    return min(keys)

def manifest():
    keys=[shape_key(s) for s in SHAPES]
    assert len(set(keys))==len(keys)
    assert not set(TRAIN_UNIONS)&set(TEST_UNIONS)
    assert not set(TRAIN_MAPS)&set(HELD_MAPS)
    assert set(sum((list(MAPS[i]) for i in TRAIN_MAPS),[]))==set(range(7))
    # Every held-out primitive operation/argument feature is present at that
    # constructor position in training; only their joint structure is absent.
    primitive_support=[]
    for s in HELD_SHAPES:
        missing=[]
        for row in range(4):
            for col in range(3):
                if SHAPES[s][row][col] not in {SHAPES[t][row][col] for t in TRAIN_SHAPES}:
                    missing.append([row,col,SHAPES[s][row][col]])
        primitive_support.append(dict(shape=s, unseen_input_features=missing))
    return dict(shapes=SHAPES,names=SHAPE_NAMES,shape_keys=keys,unions=UNIONS,maps=MAPS,
                resulting_layouts=[layout_for(p) for p in MAPS],groups=GROUPS,
                primitive_support=primitive_support,whole_shape_id_is_model_input=False,
                union_pair_id_is_model_input=False,mapping_id_is_model_input=False)

def seed_inputs(cases):
    c=np.asarray(cases); plans=np.array(SHAPES)[c[:,0]]
    u=np.array(UNIONS)[c[:,1]]; m=np.array(MAPS)[c[:,2]]
    return np.concatenate((np.eye(2)[plans[:,:,0]].reshape(len(c),-1),
        np.eye(10)[plans[:,:,1:]].reshape(len(c),-1), np.eye(8)[u].reshape(len(c),-1),
        c[:,3:4], np.eye(8)[c[:,4:6]].reshape(len(c),-1),
        np.eye(7)[m].reshape(len(c),-1), ((c[:,6,None]>>np.arange(4))&1)),axis=1).astype(np.float32)

def sample(group,n,rng):
    ss,us,ms=GROUPS[group]
    out=np.zeros((n,7),np.int32)
    out[:,0]=rng.choice(ss,n);out[:,1]=rng.choice(us,n);out[:,2]=rng.choice(ms,n)
    out[:,3]=rng.integers(0,2,n);out[:,6]=rng.integers(0,16,n)
    for i in range(n):
        # A mix of direct equality, potentially congruent outputs and other queries.
        mode=i%3
        out[i,4:6]=UNIONS[out[i,1]] if mode==0 else PAIRS[int(rng.integers(len(PAIRS)))] if mode==1 else UNIONS[6+int(rng.integers(6))]
    return out

def positions(n,rng):
    start=rng.integers(0,2048,n); gaps=rng.integers(1,32,(n,2))
    return np.column_stack((start,start+gaps[:,0],start+gaps.sum(axis=1))).astype(np.int32)

def digest(array):
    return hashlib.sha256(np.asarray(array,dtype=np.int32).tobytes()).hexdigest()
