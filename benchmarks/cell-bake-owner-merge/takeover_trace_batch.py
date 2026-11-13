"""Batch static catalog extensions from an audited takeover-aware trace.

Run under eggfuse-job --kind compute. Arguments: OUTPUT_ROOT SEED_PROGRAM
BASELINE_MEMORY SELECTOR_BINARY MEMORY_BINARY. OUTPUT_ROOT/trace.json must exist.
The memory binary measures standalone Cell runtime; this is not a timing test.
"""
import json, pathlib, subprocess, collections, sys
root, seed, baseline_path, selector, memory_binary = sys.argv[1:]
root = pathlib.Path(root)
trace=json.loads((root/'trace.json').read_text())
assert trace['all_saved_run_checks_equal'] and trace['completed_owners'] and trace['retired_prefixes']
rows=trace['catalog_trace']['records']
def distribution(rows):
    result=collections.Counter()
    for r in rows: result[len(r['fragment']['hops'])]+=1
    return dict(sorted(result.items()))
summary={'runs':trace['runs'],'records':len(rows),'hop_distribution':distribution(rows),'eligible_hop_distribution':distribution([r for r in rows if r['matched_births']>1 and r['available_shared_inputs']>0]),'saturation':{}}
for r in trace['catalog_trace']['saturation']['rows']:
    k=r['outcome']; summary['saturation'][k]=summary['saturation'].get(k,0)+r['counts']['applications']
summary['batches']=[]
for budget in (32,128,256):
    d=root/f'budget{budget}'
    subprocess.run([selector,seed,str(root/'trace.json'),str(budget),str(d)],check=True)
    selected=json.loads((d/'selection.json').read_text())
    subprocess.run([memory_binary,str(d/'program.json'),str(d/'memory.json'),'inherited-owners','--port-domains-only','--cell-fields','--retired-prefixes','--state-output',str(d/'state.json')],check=True,stdout=subprocess.DEVNULL)
    m=json.loads((d/'memory.json').read_text()); baseline=json.loads(pathlib.Path(baseline_path).read_text())
    summary['batches'].append({'budget':budget,'added_fragments':selected['added_fragments'],'replaced_prefixes':selected['replaced_prefixes'],'graph_bytes':m['graph_owned_teardown_bytes'],'program_bytes':m['retained_program_teardown_bytes'],'same_final_digest':m['final_state_sha256']==baseline['final_state_sha256'],'same_runs':m['run_sequence']==baseline['run_sequence']})
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
