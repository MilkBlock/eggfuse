"""Proof rejection checks, including cancellation hiding an unsafe intermediate."""
import copy,json
from pathlib import Path
from compiler import Affine,Unsupported,LIMIT,I64_MAX,checked_reference
rule=json.loads(Path(__file__).with_name('rule.json').read_text())['rule']
plan=Affine(rule,[1,2],[1<<20,1<<20])
assert plan.eligible([0,2]) and not plan.eligible([I64_MAX,2]) and not plan.eligible([float('nan'),2])
assert not plan.eligible([True,2]) and not plan.eligible([0])
def rejects(r,bounds):
 try:Affine(r,[1,2],bounds)
 except Unsupported:return
 raise AssertionError('unsafe program accepted')
rejects(rule,[LIMIT,LIMIT])
# a+1 may round before a later cancellation: proving just the final zero is insufficient.
bad=copy.deepcopy(rule);bad['effects'][4]['args']=[{'slot':8},{'slot':8}]
rejects(bad,[LIMIT,1])
bad=copy.deepcopy(rule);bad['effects'][3]['call']['primitive']='/'
rejects(bad,[100,100])
bad=copy.deepcopy(rule);bad['effects'][3]['call']['primitive']='*';bad['effects'][3]['args']=[{'slot':1},{'slot':2}]
rejects(bad,[100,100])
bad=copy.deepcopy(rule);bad['effects'][3]['args'][0]={'slot':6}
rejects(bad,[100,100])
assert checked_reference(rule,[1,2],[I64_MAX,2]) is None
print('range, intermediate overflow, unsupported op, type and dependency rejection: pass')

good=copy.deepcopy(rule);good['effects'][3]['call']['primitive']='*';good['effects'][3]['args'][1]['literal']=3
compiled=Affine(good,[1,2],[100,100])
for values in [[-100,2],[100,100],[0,3]]:
 expected=checked_reference(good,[1,2],values)
 assert (values@compiled.coefficients+compiled.bias).tolist()==expected
print('constant multiplication certificate and outputs: pass')
