"""Static compiler vocabulary for the bounded Seed/F/G example; no instance oracle."""
DIM = 128
ROLES = ('a', 'b', 'u', 'v', 'w', 'empty')
OWNERS = ('input', 'A', 'B')
PROOFS = ('build', 'merge_f', 'preserve', 'extend_transfer', 'defer')
PREMISES = ('seed', 'same', 'build', 'union', 'initial_eq', 'none')
SPECS = {
    'layout': (5, 6), 'alias': (4, 6), 'owner': (1, 3),
    'proof': (1, 5), 'premises': (3, 6), 'g_arg': (1, 6),
    'eq': (10,), 'pending': (2,), 'retired': (1,), 'payload': (8,),
}
CATEGORICAL = {k for k, v in SPECS.items() if len(v) == 2}
OFFSETS = {}
WIDTH = 0
for key, shape in SPECS.items():
    size = 1
    for n in shape: size *= n
    OFFSETS[key] = (WIDTH, WIDTH + size)
    WIDTH += size
PAIRS = [(i, j) for i in range(5) for j in range(i + 1, 5)]
