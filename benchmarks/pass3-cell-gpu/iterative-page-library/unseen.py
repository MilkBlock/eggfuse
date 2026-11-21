"""Load the same frozen page-library weights on a truly different compiled source interface."""
import argparse,json
from pathlib import Path
from driver import source,base,route
from policy import shapes,deploy


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    p=a.fixture/'compiled/program.json';b=a.fixture/'bundle';plans=b/'plans.json'
    rows=shapes(json.loads(p.read_bytes()),json.loads(plans.read_bytes()));keys={v[0] for v in rows if v}
    training=json.loads(a.learning.read_bytes());assert keys-set(training['features'])
    req=json.loads((b/'request.json').read_bytes());req.pop('merge_config',None)
    t=a.exp/'baked-port-packed-study-v1'
    req.update(single_config=str(b/'single.json'),root_config=str(b/'root.json'),multi_weights=str(t/'sum-bits-1703-tied.json'),baked_codes=str(t/'sum-bits-1703-tied.bin'),multi_mode='rowdeltapairguardstackseal2xlearned',radius=0,packed_lookup=True,multi_generation='complete',multi_root_pages=True,audit=True)
    with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as ref:gold=ref({'audit':True})
    report={}
    with source.base.session(a.native,p,plans) as infer:
        for arm in ('off','all','iterated','return-0-1703','return-8-1703'):
            selected=set() if arm=='off' else keys if arm=='all' else set(deploy(rows,training['policies'][arm]))
            out=infer(route(req,rows,selected));assert 'source_error' not in out,out.get('source_error')
            assert all(out[k]==gold[k] for k in ('rhs','writes','resumes','schedule','runs','state_sha'))
            assert [[e for e in run if e[0]=='union'] for run in out['events']]==gold['unions'] and any(gold['unions'])
            entry=dict(available=len(keys),unknown=len(keys-set(training['features'])),selected=len(keys&selected),graph=out['state_sha'],raw=out['multi']['raw_sha256'],
                      calls=out['multi']['page_library'],cells=out['cell_ids'],source_rhs=out['rhs'])
            if report:
                for k in ('graph','raw','cells','source_rhs'):assert entry[k]==report['off'][k]
            report[arm]=entry
    (a.out/'unseen.json').write_text(json.dumps(report,separators=(',',':'))+'\n')
    print([(k,v['unknown'],v['selected']) for k,v in report.items()])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','learning','fixture','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
