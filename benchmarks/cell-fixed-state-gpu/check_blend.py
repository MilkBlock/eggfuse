"""Check exact compiled blend against its two independent GPU branches."""
import argparse,json
from pathlib import Path
import numpy as np
import mlx.core as mx
import run as base
from gpu_model import forward
from train_augmented import read_checked
p=argparse.ArgumentParser()
for k in ('corpus','stress_runtime','left','right','compiled','selection'):p.add_argument('--'+k.replace('_','-'),type=Path,required=True)
a=p.parse_args()
if not mx.metal.is_available():raise RuntimeError('GPU required')
mx.set_default_device(mx.gpu)
left,right,compiled=[dict(np.load(getattr(a,k))) for k in ('left','right','compiled')];alpha=json.loads(a.selection.read_text())['selection']['alpha']
base.D=int(left['dimension']);base.POOL_OPS=bool(left['pool_ops']);base.OP=left['op'];base.EDGE=left['edge'];base.LITERAL=left['literal']
rows=json.loads(a.corpus.read_text())['records']+read_checked(a.stress_runtime);raw=[]
for r in rows:
 plan=base.Plan(r['entry']);raw.append(plan.project(plan.gather(r['entry'])))
raw=np.array(raw)
def execute(m):
 x=raw if 'state_projection' not in m else raw@m['state_projection']+m['state_bias']
 y=forward(m)(mx.array(x));mx.eval(y);return np.array(y)
expected=(1-alpha)*execute(left)+alpha*execute(right);actual=execute(compiled)
np.testing.assert_allclose(actual,expected,atol=.003,rtol=.003);assert np.array_equal(actual.argmax(1),expected.argmax(1))
print(json.dumps(dict(rows=len(rows),max_error=float(abs(actual-expected).max()),top1_equal=True,status='pass')))
