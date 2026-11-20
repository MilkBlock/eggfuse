"""Build a source fixture where a function write, a target and a later union independently enable results."""
from pathlib import Path
import argparse,json,sys,subprocess
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'request-route-policy'))
from driver import bridge
base=bridge.parent.base


def fixture(a):
    a.out.mkdir(parents=True,exist_ok=False)
    p=a.out/'compiled/program.json';bundle=a.out/'bundle'
    subprocess.run(['cargo','cell-compile','--source',HERE/'activation.egg','--output',p.parent],check=True)
    subprocess.run([sys.executable,HERE.parent/'codec.py',p,a.out/'img'],check=True)
    subprocess.run([sys.executable,HERE.parent/'joint-witness/prepare.py',p,a.out/'img',bundle],check=True)
    plans=bundle/'plans.json';r=json.loads((bundle/'request.json').read_bytes());r.pop('merge_config',None)
    weights=a.exp/'baked-port-packed-study-v1'
    (bundle/'root.json').write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    r.update(radius=0,multi_generation='complete',multi_mode='rowdeltapairguardstackseal2xlearned',
             baked_codes=str(weights/'sum-bits-1703-tied.bin'),multi_weights=str(weights/'sum-bits-1703-tied.json'),
             single_config=str(bundle/'single.json'),root_config=str(bundle/'root.json'),packed_lookup=True,
             multi_root_pages=True,connected_requests=bridge.extract(json.loads(p.read_bytes()),json.loads(plans.read_bytes())),audit=True)
    assert any(r['connected_requests'])
    with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as cpu:gold=cpu({'audit':True})
    report={}
    with base.session(a.native,p,plans) as infer:
        for name,updates in [('direct',{}),('offset',dict(wake_roots=3)),('patch',dict(wake_roots=3,patch_subscriptions=3)),('lost',dict(wake_roots=3,patch_subscriptions=4))]:
            v=infer(dict(r,**updates))
            assert 'source_error' not in v,v.get('source_error')
            assert all(v[k]==gold[k] for k in ('rhs','writes','resumes','runs','schedule','state_sha'))
            unions=[[e for e in z if e[0]=='union'] for z in v['events']]
            assert unions==gold['unions'] and any(unions)
            wins=v['multi']['tickets']; parents=[{k:t[k] for k in ('rule','run','anchors','inputs','ordinal')} for t in wins]
            winner_runs=sorted({t['run'] for t in wins if r['connected_requests'][t['rule']]})
            assert winner_runs==[1,3,5,7],winner_runs
            summary=dict(winners=parents,source={k:gold[k] for k in ('rhs','writes','resumes','schedule','unions')},
                         state=v['state_sha'],cells=v['cell_ids'],raw=v['multi']['raw_sha256'],wake=v['multi']['wake'],patch=v['multi']['patch_ports'])
            if name!='direct':
                assert summary['wake']['routed_calls']>0
                for key in ('winners','source','cells','state','raw'):assert summary[key]==report['direct'][key]
            report[name]=summary
    (a.out/'fixture.json').write_text(json.dumps(report,separators=(',',':'))+'\n')
    print('Enabled source winners at Runs',winner_runs,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    fixture(p.parse_args())
