"""Consume states computed directly by native Graph.slot; verify then batch on GPU."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import run as base
p=argparse.ArgumentParser()
for k in ('states','corpus','model','output'):p.add_argument('--'+k,type=Path,required=True)
a=p.parse_args();export=json.loads(a.states.read_text());model=dict(np.load(a.model));corpus=json.loads(a.corpus.read_text())
if export['model_sha256']!=hashlib.sha256(a.model.read_bytes()).hexdigest():raise ValueError('model identity mismatch')
base.D=int(model['dimension']);base.POOL_OPS=bool(model['pool_ops']);base.OP=model['op'];base.EDGE=model['edge'];base.LITERAL=model['literal']
rows={r['id']:r for r in corpus['records'] if r['split']=='test'};cases=export['cases']
if len(cases)!=len(rows) or {c['id'] for c in cases}!=set(rows):raise ValueError('incomplete test instances')
reference=[]
for c in cases:
    r=rows[c['id']];plan=base.Plan(r['entry']);reference.append(plan.project(plan.gather(r['entry'])))
x=np.array([c['state'] for c in cases],np.float32);reference=np.array(reference)
np.testing.assert_allclose(x,reference,atol=1e-4,rtol=1e-4)
import mlx.core as mx
if not mx.metal.is_available():raise RuntimeError('GPU required')
mx.set_default_device(mx.gpu)
l,pj,q,n,b=[mx.array(model[k]) for k in ('linear','first','first_bias','nonlinear','bias')];degree=int(model['degree'])
def forward(x):return x@l+(x@pj+q)**degree@n+b
fn=mx.compile(forward);v=mx.array(x);mx.eval(fn(v));samples=[]
for _ in range(15):
    start=time.perf_counter();out=fn(v);mx.eval(out);samples.append((time.perf_counter()-start)*1000)
scores=np.array(out);ref=np.array(fn(mx.array(reference)));assert np.array_equal(scores.argmax(1),ref.argmax(1))
labels=list(model['labels']);truth=np.array([labels.index(rows[c['id']]['completion_key']) for c in cases])
result=dict(scope='Fresh native instances -> Graph.slot affine state -> serialized batch -> Metal GPU; bench only, no completion effects',
    correct=int((scores.argmax(1)==truth).sum()),total=len(cases),native_python_state_max_error=float(abs(x-reference).max()),
    top1_equal=True,native_projection_ns_per_case_median=float(np.median([c['projection_nanoseconds'] for c in cases])),
    native_projection_ns_batch_sum=float(sum(c['projection_nanoseconds'] for c in cases)),gpu_batch_ms_median=float(np.median(samples)),
    caveats=['native timing is warm release-build projection only','serialization and subprocess transport excluded, not a fused end-to-end timing',
        'addresses pinned to unchanged fresh initial fixtures; no general cross-stage binding or generation handling'],
    hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('states','corpus','model')})
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
