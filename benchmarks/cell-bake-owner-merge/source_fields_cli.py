"""Short CLI differential check. Run inside the shared compute queue."""
import json, pathlib, subprocess, hashlib, sys, runpy
root=pathlib.Path(__file__).resolve().parents[2]
lease=runpy.run_path(str(root/'tools/local_jobs.py'))['current_lease']()
if not __debug__ or lease is None or lease['kind']!='compute':
 raise SystemExit('Run without Python -O, inside eggfuse-job run --kind compute')
compiler,runtime,out=map(lambda x:pathlib.Path(x).resolve(),sys.argv[1:])
out.mkdir(exist_ok=False)
subprocess.run([str(compiler),'compile','--source',str(root/'tools/cell-compiler/tests/fixtures/cell-point-queries.egg'),'--output',str(out/'compiled')],check=True,stdout=subprocess.DEVNULL)
program=out/'compiled/program.json'
reports={}
for lane,flags in [('serial',[]),('workers',['--query-workers','2','--query-grain','1']),('cell-workers',['--query-workers','2','--query-grain','1','--cell-fields'])]:
 subprocess.run([str(runtime),'--program',str(program),'--output',str(out/lane),'--local-congruence','--audit-stages',*flags],check=True,stdout=subprocess.DEVNULL)
 reports[lane]=json.loads((out/lane/'report.json').read_text())
for name in ['state.json','stages.json','binding-audit.json']:
 values=[json.loads((out/lane/name).read_text()) for lane in reports]
 assert all(value==values[0] for value in values),name
assert reports['workers']['query_workers']['stats']['batches']>0
assert all(n>0 for n in reports['cell-workers']['query_workers']['stats']['worker_steps'])
assert reports['cell-workers']['stable_ports']['stats']['cell_fields']
assert reports['cell-workers']['stable_ports']['materialized_stable_nodes']==0
assert reports['workers']['stable_ports']['materialized_stable_nodes']>0
result={'scope':'standalone Cell CPU short CLI differential check, not native acceptance or timing','runtime_sha256':hashlib.sha256(runtime.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256((root/'tools/cell-compiler/tests/fixtures/cell-point-queries.egg').read_bytes()).hexdigest(),'runs':len(reports['serial']['steps']),'checks':['state.json','stages.json','binding-audit.json'],'lanes':{k:{'batches':v['query_workers']['stats']['batches'] if v['query_workers']['enabled'] else 0,'materialized_stable_nodes':v['stable_ports']['materialized_stable_nodes'],'cell_scalar_reads':v['stable_ports']['stats']['cell_scalar_reads']} for k,v in reports.items()}}
(out/'checked.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
