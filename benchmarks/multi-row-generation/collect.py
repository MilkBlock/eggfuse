"""Collect every predeclared model and checked timing; never choose a winner."""
import argparse,hashlib,json,shutil,ast
from pathlib import Path
import numpy as np
from importlib.metadata import version

p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
source=Path(__file__).parent
# Preserve exact executed driver bytes. The checked-in driver is allowed only
# whitespace cleanup after execution; model/task source must remain identical.
(source/'results/direction').mkdir(parents=True,exist_ok=True)
executed=json.loads((source/'results/direction/executed-driver.json').read_text())
assert hashlib.sha256(executed['source'].encode()).hexdigest()==executed['sha256']
assert ast.dump(ast.parse(executed['source']))==ast.dump(ast.parse((source/'run.py').read_text()))
(a.output/'executed-driver.json').write_text(json.dumps(executed,indent=2)+'\n')
summary={};model_reports={}
for mode in ('joint','independent'):
 for seed in (1703,1709):
  base=a.root/f'{mode}-{seed}';r=json.loads((base/'result.json').read_text());timing=json.loads((base/'checked-timing.json').read_text())
  for name,digest in r['protocol']['source_sha256'].items():
   actual=executed['sha256'] if name=='run.py' else hashlib.sha256((source/name).read_bytes()).hexdigest()
   assert actual==digest,name
  key=f'{mode}-{seed}';shutil.copyfile(base/'result.json',a.output/f'{key}.json');shutil.copyfile(base/'checked-timing.json',a.output/f'{key}-timing.json')
  with np.load(base/'final_fanin_rows.npz') as z:
   degree_bad=0
   for g in range(len(z['a'])):
    keymap={int(row[0]):i for i,row in enumerate(z['a'][g])};bmap={int(row[0]):row for row in z['b'][g]}
    targets=[keymap[int(bmap[int(row[0])][1])] for row in z['a'][g]]
    degree_bad+=len(set(targets))<len(targets)
   assert degree_bad==256
  report=dict(status=r['status'],panels={name:dict(passed=v['whole_graph_passed'],graphs=v['graphs'],
     cross_row_correct=v['cross_row_successor_correct'],cross_row_total=v['cross_row_successor_obligations'],
     missing=v['missing_or_invalid_obligations'],cpu_decoder_agrees=v['cpu_decoder_agrees']) for name,v in r['panels'].items()},
     erased_first_latent_passed=r['erased_first_latent']['whole_graph_passed'],lineage=r['lineage'],
     model_sha256=r['model_sha256'],fresh_nonbijective_graphs=degree_bad,
     timing={name:dict(parallel_ms=v['lanes']['parallel']['host_features_forward_check_median_ms'],
        serial_ms=v['lanes']['serial_cached_queries']['host_features_forward_check_median_ms'],
        speed_ratio=v['host_speed_ratio'],complete=v['lanes']['parallel']['whole_graph_passed'],
        graphs=v['lanes']['parallel']['graphs'],decoded_equal=v['decoded_equal'],
        complete_graphs_per_second=v['lanes']['parallel']['host_complete_graphs_per_second']) for name,v in timing['panels'].items()})
  model_reports[key]=report
summary=dict(driver_format_only_change=dict(executed_sha256=executed['sha256'],checked_in_sha256=hashlib.sha256((source/'run.py').read_bytes()).hexdigest(),same_python_ast=True),scope='bounded same-graph two-stage neural generation; not full architecture proof',models=model_reports,
    artifacts=str(a.root),readout_bound_gpu_checks=True,cpu_corrections=0,
    baseline_limit='cached serial emission of same queries, not trained autoregression',
    output_placement='source-anchored, not learned free row allocation',
    environment=dict(mlx=version('mlx'),numpy=version('numpy')),
    unfinished=['strong autoregressive baseline','free allocation and variable match multiplicity','union','ownership conflict coordination','real eggcc','strong canonical latent contract'])
(a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for key,r in model_reports.items():print(key,r['status'],[(k,v['passed']) for k,v in r['panels'].items() if k.startswith('final_')])
