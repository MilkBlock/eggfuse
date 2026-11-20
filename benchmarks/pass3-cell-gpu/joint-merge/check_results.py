"""Verify independent physical id credits and the negative/fallback controls for the combined run."""
import json
from pathlib import Path


def check(root):
    read=lambda n:json.loads((root/n).read_text())
    data=read('results.json');trace=read('physical-ids.json');timing=read('timings.json')
    assert set(data)==set(trace)==set(timing) and len(data)==8
    for case,r in data.items():
        learned=r['learned'];physical=trace[case]['children']
        assert len({row[0] for row in physical})==len(physical)==learned['extra_direct']==learned['counts'][5]
        assert all(t!=parent_t and source in ('multi','single') for _,t,_,parent_t,source,*_ in physical)
        assert learned['source_exact'] and learned['direct_union']==learned['base_direct']+len(physical)
        assert 100*learned['direct_union']>=98*learned['total_fresh'] and 100*learned['neural_rhs']>=98*learned['total_rhs']
        for n in ('null','shadow','wrong-operands','wrong-template','stale'):
            assert r[n]['source_exact'] and r[n]['extra_direct']==0 and r[n]['base_direct']==learned['base_direct']
        assert all(r[n]['raw_gate_hash']==learned['raw_gate_hash'] for n in ('shadow','wrong-operands','wrong-template','stale'))
        assert r['null-no-fallback']['first_uncompleted_run']>0
        assert (r['learned-no-fallback'].get('first_uncompleted_run') is None)==case.startswith('stable-argmax')
        assert r['all']['extra_direct']>=len(physical)
        assert all(len(v['inference_ms'])==len(v['rpc_ms'])==8 for v in timing[case].values())
    print('Verified combined direct-template physical coverage, independent child ids, immutable producer stamps, negative controls and timings.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
