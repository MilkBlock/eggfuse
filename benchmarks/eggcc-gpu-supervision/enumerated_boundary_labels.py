"""Final boundary Eq labels from native private seed anchors, never Run guesses."""
from synthetic_cell_inputs import validate
from device_snapshot_import import identity


def label(document,trace):
    _,snapshot=validate(document)
    if not all(trace.get(k)is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('native audit required')
    ports=[];seen=set()
    for row in snapshot['rows']:
        for v in row['values']:
            if 'eq' in v and identity(v) not in seen:ports.append(v);seen.add(identity(v))
    seeds={'SyntheticSeed_'+v['sort'] for v in ports};found={}
    for row in trace['final']['rows']:
        if row['table'] not in seeds:continue
        values=row['values']
        if row['subsumed'] or len(values)!=2:raise ValueError('invalid seed fact')
        index=values[0].get('value')
        if type(index)is not int or not 0<=index<len(ports) or values[0]['sort']!='i64':raise ValueError('invalid seed index')
        if row['table']!='SyntheticSeed_'+ports[index]['sort'] or values[1]['sort']!=ports[index]['sort'] or 'eq' not in values[1]:raise ValueError('seed sort mismatch')
        if index in found:raise ValueError('duplicate seed anchor')
        found[index]=identity(values[1])
    if set(found)!=set(range(len(ports))):raise ValueError('missing seed anchor')
    classes={};partition=[classes.setdefault(found[i],len(classes)) for i in range(len(ports))]
    return dict(scope='program-final equivalence of enumerated boundary ports; no retirement proof',input_sha256=document['input_sha256'],ports=ports,partition=partition,classes=len(classes),input_classes=len(ports),new_boundary_equalities=len(ports)-len(classes))


def main():
    import argparse,json,tarfile,hashlib
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    manifest=json.loads((a.directory/'manifest.json').read_text());labels=[]
    for record in manifest['records']:
        if record['status']!='pass':continue
        path=a.directory/(str(record['index'])+'.tar.gz')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['archive_sha256']:raise ValueError('archive provenance')
        with tarfile.open(path) as t:
            raw=t.extractfile('case/trace.json').read()
            if hashlib.sha256(raw).hexdigest()!=record['trace_sha256']:raise ValueError('trace provenance')
            document=json.load(t.extractfile('case/input.json'));trace=json.loads(raw)
            if document['input_sha256']!=record['input_sha256'] or trace['program_sha256']!=record['program_sha256']:raise ValueError('record provenance')
            labels.append(dict(index=record['index'],**label(document,trace)))
    a.output.write_text(''.join(json.dumps(row)+'\n' for row in labels))
    print(json.dumps(dict(labeled=len(labels),unresolved=manifest['expected_inputs']-len(labels),new_boundary_equalities=sum(r['new_boundary_equalities'] for r in labels))))
if __name__=='__main__':main()
