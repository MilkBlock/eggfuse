"""Verify baked projection for independent scalar values, without closure labels."""
import argparse
import copy
import json
import numpy as np
from run import Plan, structure, digest, reference

p=argparse.ArgumentParser()
p.add_argument('--corpus',required=True)
a=p.parse_args()
rows=json.load(open(a.corpus))['records']
seen=set();rng=np.random.default_rng(72);checks=0
for row in rows:
    key=digest(structure(row['entry']))
    if key in seen:continue
    seen.add(key);plan=Plan(row['entry'])
    for _ in range(3):
        entry=copy.deepcopy(row['entry'])
        for n,f,pos in plan.reads:
            entry[n][f][1][pos][2]=int(rng.integers(-8,9))
        np.testing.assert_allclose(plan.project(plan.gather(entry)),reference(entry),atol=1e-4,rtol=1e-4)
        checks+=1
print(json.dumps(dict(layouts=len(seen),independent_scalar_checks=checks,status='pass')))
