"""Bounded native/independent-reference diagnosis, never a saturation label."""
import argparse,json,tarfile,tempfile,hashlib
from pathlib import Path
from collect_enumerated_native import execute,archive_case
from synthetic_cell_inputs import validate
from synthetic_native_source import emit
from audit_native_synthetic import compare
from enumerated_boundary_labels import label
from reference_union_family import Reference
from device_snapshot_import import identity


def reference_growth(document,runs):
    recipe,snapshot=validate(document);ids={}
    for row in snapshot['rows']:
        for value in row['values']:ids.setdefault(identity(value),len(ids))
    ref=Reference(recipe,snapshot['rows'],ids);records=[]
    for _ in range(runs):
        before_u=ref.unions;before_c=ref.constructions;changed,applications=ref.apply(recipe['rules'])
        records.append(dict(changed=changed,applications=applications,facts=len(ref.normalized_facts()),new_unions=ref.unions-before_u,new_constructors=ref.constructions-before_c))
    return records


def main():
    p=argparse.ArgumentParser()
    for k in ('capture','output','compiler','observer'):p.add_argument(k,type=Path)
    p.add_argument('--runs',type=int,default=8);a=p.parse_args()
    if a.runs<1:raise ValueError('positive bound required')
    manifest=json.loads((a.capture/'manifest.json').read_text());a.output.mkdir(parents=True,exist_ok=False);records=[]
    for rec in manifest['records']:
        if rec['status']=='pass':continue
        path=a.capture/(str(rec['index'])+'.tar.gz')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=rec['archive_sha256']:raise ValueError('archive mismatch')
        with tarfile.open(path) as t:document=json.load(t.extractfile('case/input.json'))
        recipe,_=validate(document);stages={r['metadata']['source_set'] for r in recipe['rules']}
        if len(stages)!=1:raise ValueError('single stage diagnosis only')
        schedule=dict(repeat=a.runs,body=dict(run=next(iter(stages))))
        record=dict(index=rec['index'],input_sha256=rec['input_sha256'],reference=reference_growth(document,a.runs))
        with tempfile.TemporaryDirectory(prefix='eggfuse-growth-') as tmp:
            folder=Path(tmp);source=folder/'input.egg';source.write_text(emit(document,schedule))
            commands=[[str(a.compiler),'compile','--source',str(source),'--output',str(folder/'compiled')],[str(a.observer),str(folder/'compiled/program.json'),str(folder/'trace.json'),'--relations','--snapshot-runs='+','.join(map(str,range(a.runs+1)))]]
            for phase,cmd in enumerate(commands):
                with (folder/(str(phase)+'.log')).open('w') as log:result=execute(cmd,log,2 if phase==0 else 1)
                if result.returncode:raise ValueError('native bounded diagnosis failed')
            trace=json.loads((folder/'trace.json').read_text())
            proof=compare(document,trace,schedule)
            if not proof['passed']:raise ValueError(proof)
            record['boundary_partitions']=[label(document,dict(trace,final=b['graph']))['partition'] for b in trace['boundaries']]
            record.update(comparison=proof,native_facts=[sum(not r['table'].startswith('SyntheticSeed_') for r in b['graph']['rows']) for b in trace['boundaries']],archive_sha256=archive_case(folder,a.output/(str(rec['index'])+'.tar.gz')))
        records.append(record)
        (a.output/'report.json').write_text(json.dumps(dict(scope='bounded growing-graph diagnosis; no final saturation labels',bound=a.runs,records=records),indent=2)+'\n')
        print(json.dumps(dict(index=rec['index'],facts=record['native_facts'])),flush=True)
if __name__=='__main__':main()
