"""Check current source references and preserve compact allocator curves from the measured native runs."""
import argparse,csv,hashlib,json
from pathlib import Path


def read(p):return json.loads(p.read_bytes())
def main(a):
    out=Path(__file__).resolve().parent
    r=read(a.data/'results.json');rows=[]
    header=('workload','arm','run','requested_heap_bytes','rss_after_bytes','ordinary_source_frames','completed_source_descriptors',
            'integral_instances','integral_view_handles','integral_live_facts','integral_fact_exceptions','integral_array_bytes')
    for n,record in r.items():
        folder=a.data/n;source=a.ref/f'events-{n}';official={k:read(source/f'{k}.json') for k in ('rhs','writes','resumes','state')}
        schedules=read(source/'report.json')['steps']
        for lane,v in record['arms'].items():
            native=read(folder/f'audit-{lane}'/'result.json');assert read(folder/f'state-{lane}.json')==official['state']
            assert len(native['stage_checks'])==len(schedules)
            for i,s in enumerate(native['stage_checks']):
                assert all(s[6+j]==[official[k][i]] for j,k in enumerate(('rhs','writes','resumes')))
                assert s[:6]==[schedules[i][k] for k in ('ruleset','path','iterations','epoch','executed_bindings','changed')]
            traces=read(folder/f'memory-{lane}.json');v['current_source_audit']=True
            curves=v.pop('curves');v['rss_peak_bytes']=max(max(x['rss_before'],x['rss_after']) for x in traces['samples'])
            v['index_and_forwarding']=dict(graph_teardown_by_field=dict(traces['graph_fields']),
                member_root_directory_estimated_bytes=traces['integral']['storage']['root_directory_payload_estimate_bytes'],
                source_id_directory=traces['source_storage'].get('source_id_directory'))
            v['combined_retained_bytes']=sum(v['memory'][k] for k in ('graph_owned_teardown_bytes','integral_instance_teardown_bytes','integral_library_teardown_bytes'))
            for x in curves:rows.append([n,lane,x['run'],x['heap'],x['rss'],*[x['records'][f] for f in header[5:]]])
        masks=read(folder/'mask.json');record['admission_mask_sha256']=hashlib.sha256(json.dumps(masks,separators=(',',':')).encode()).hexdigest()
    (out/'storage-results.json').write_text(json.dumps(r,indent=1)+'\n')
    with (out/'storage-curves.tsv').open('w') as f:
        writer=csv.writer(f,delimiter='\t',lineterminator='\n');writer.writerow(header);writer.writerows(rows)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data',type=Path);p.add_argument('ref',type=Path);main(p.parse_args())
