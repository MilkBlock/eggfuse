import json
from pathlib import Path
HERE=Path(__file__).parent
load=lambda n:json.loads((HERE/n).read_bytes())
controls=load('controls.json');early=load('run819.json');complete=load('complete.json')
exact=controls['same_build_exact'];older=controls['legacy_joint']
assert exact['runs']==older['runs']==5687 and exact['state']==older['state']==exact['gold_state']
assert all(v is None for v in exact['diff'].values()) and older['aligned'] and older['exhausted']>0
e,b,h=[early[str(k)] for k in (0,1000000,8000000)]
assert e['rhs']==h['rhs']==12914 and b['rhs']==9794
assert e['row_sha']==h['row_sha']!=b['row_sha'] and e['state']==h['state']!=b['state']
assert len(b['delta'])==1 and b['delta']['249']['missing_count']==3120 and b['delta']['249']['extra_count']==0
assert b['exhausted']==[[819,249,1000000,1000000,5]] and not h['exhausted']
whole=complete['8000000']
assert whole['state']==exact['state'] and whole['runs']==exact['runs']
metrics=whole['full_checks']
assert metrics['aligned'] and all(metrics['checks'].values()) and metrics['rhs']==metrics['neural_rhs']==635818
assert metrics['direct_cells']*100>=98*metrics['fresh']
print('Verified the source controls, the isolated 3,120 omissions, the restored exact Run and the complete Deriche audit.')
