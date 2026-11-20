import csv,json
from collections import Counter
from pathlib import Path


def check(root):
    load=lambda n:json.loads((root/n).read_bytes())
    r=load('storage-results.json');parent=load('parent-ports.json');merge=load('merge-ports.json')
    with (root/'storage-curves.tsv').open() as f:counts=Counter((x['workload'],x['arm']) for x in csv.DictReader(f,delimiter='\t'))
    for n,c in r.items():
        d,l,s=(c['arms'][k] for k in ('dynamic','leaf','composed'))
        assert c['exact_admissions']==len(load(f'admit-{n}.json'))==l['admissions']==d['admissions']==s['admissions']
        assert len(load(f'library-{n}.json')['edges'])==c['library_units']==32
        assert d['graph']==l['graph']==s['graph'] and all(x['current_source_audit'] for x in (d,l,s))
        assert d['physical']['integral_instances']==0 and l['physical']['integral_instances']-s['physical']['integral_instances']==s['composition']['layout_switches']>0
        assert s['physical']['integral_live_facts']==l['physical']['integral_live_facts']==s['view_checks']['final_members'][2]>0
        assert l['view_checks']['peak_multi_run_instances']<s['view_checks']['peak_multi_run_instances']
        for k,v in c['arms'].items():assert counts[n,k]==c['semantic_runs']==v['runs'] and len(v['samples_ms'])==6
    for n in parent:
        assert set(parent[n]['lookup_reasons'])<= {'0','1'} and parent[n]['all_observed_graphs_and_ordered_reference_events_equal']
        assert merge[n]['merge_ports']['source_merge_effect_exact']>0
    print('Verified current-program matched online storage and actual producer-port census.')


if __name__=='__main__':check(Path(__file__).parent)
