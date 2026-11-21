"""Link the existing dense Cell arena into the same joint source and test the combinations."""
import argparse,hashlib,importlib.util,json,shutil,subprocess
from contextlib import ExitStack
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('joint_source',HERE/'study.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
spec=importlib.util.spec_from_file_location('stable_id_layout',HERE.parent/'paged-cell-ids/overlay.py');layout=importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    tree=a.out/'tree';subprocess.run(['cp','-cR',a.build/'tree',tree],check=True)
    layout.install(tree/'engine/cell-runtime')
    target=a.out/'target';subprocess.run(['cargo','build','--locked','--offline','--release','--target-dir',target,
        '-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit,receipt-arena',
        '--example','joint_witness_session'],cwd=tree,check=True)
    native=target/'release/examples/joint_witness_session'
    binaries={'hash':a.build/'session','arena':native}
    (a.out/'identities.json').write_text(json.dumps({k:hashlib.sha256(f.read_bytes()).hexdigest() for k,f in binaries.items()},indent=1)+'\n')
    results={}
    for name in a.cases:
        program,plans,req=entry.source.config(a,name)
        q=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192,factor_page=0)
        both=dict(factor_page=2,page_premises=9,coordinate_verify=2,ordered_effect_blocks=4,ordered_repair=7)
        arms={}
        for kind in ('hash','arena'):
            for route in ('original','joint','repair'):
                for gen in ('live','positive'):
                    if gen=='positive' and (kind,route) not in [('hash','original'),('arena','joint'),('arena','repair')]:continue
                    dec=both if route=='joint' else {'ordered_repair':7} if route=='repair' else {}
                    arms[f'{kind}-{route}-{gen}']=(kind,dict(q,**dec,receipt_oracle=gen))
        vdir=a.exp/'compact-vanilla-20261121'
        with entry.source.base.session(vdir/'vanilla-audit',program) as ref:gold=ref({'audit':True})
        with ExitStack() as stack:
            exact=stack.enter_context(entry.source.base.session(vdir/'vanilla',program))
            eng={k:stack.enter_context(entry.source.base.session(f,program,plans)) for k,f in binaries.items()}
            for f in eng.values():
                out=f(dict(q,receipt_oracle='capture'));assert out['state_sha']==gold['state_sha']
            rows={'vanilla':dict(ms=[],runs=gold['runs'],rhs=gold['rhs_count'])}
            for label,(kind,request) in arms.items():
                out=eng[kind](dict(request,audit=True));assert 'source_error' not in out,out.get('source_error')
                r=entry.source.base.summarize(out,gold);r.pop('rows');r.pop('work')
                r['verified_roots']=r.pop('neural_rhs');r['online_root_rhs']=out['online_neural_rhs']
                r['phase_ms']=[];r['store']=out.get('physical_store',{'layout':'hash'})
                assert r['online_root_rhs']==(r['rhs'] if label.endswith('live') else 0)
                if label!='hash-original-live':
                    for f in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids','rhs','direct_cells'):
                        assert r[f]==rows['hash-original-live'][f]
                if label.endswith('live') and label!='hash-original-live':
                    for f in ('raw','multi','commits','physical','children'):assert r[f]==rows['hash-original-live'][f]
                rows[label]=r;del out
            names=list(rows)
            for i in range(5):
                off=i%len(names);seq=names[off:]+names[:off]
                for label in seq if i%2 else reversed(seq):
                    if label=='vanilla':v=exact({})
                    else:
                        kind,cfg=arms[label];v=eng[kind](cfg)
                        assert v['online_neural_rhs']==rows[label]['online_root_rhs'] and v['root_recipe']['allocated']==rows[label]['root_allocated']
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if i:
                        rows[label]['ms'].append(v['ms'])
                        if label!='vanilla':rows[label]['phase_ms'].append(v['phases_ms'])
        for x in rows.values():x['median_ms']=median(x['ms'])
        results[name]=rows;(a.out/'arena.json').write_text(json.dumps(results,indent=1)+'\n')
        print(name,[(n,round(v['median_ms'],2)) for n,v in rows.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    a=p.parse_args();a.seed=1703;run(a)
