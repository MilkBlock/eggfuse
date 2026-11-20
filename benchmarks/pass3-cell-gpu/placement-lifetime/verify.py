"""Recompute lifetime exposure from every source boundary and compare the original ownership ledger."""
import json
from pathlib import Path
from analyze import analyze
from study import ARMS,CASES,sha

HERE=Path(__file__).resolve().parent


def verify(folder=HERE):
    load=lambda path:json.loads(path.read_bytes())
    previous=load(folder.parent/'prospective-owner-placement/stream.json')
    headers,*actions=[json.loads(line) for line in (folder.parent/'prospective-owner-placement/actions.jsonl').read_text().splitlines()]
    table=[dict(zip(headers,row)) for row in actions]
    means={}
    for case in CASES:
        rows=load(folder/(case+'.json'))
        assert set(rows)==set(ARMS)
        assert len({r['program_sha256'] for r in rows.values()})==1
        for arm,row in rows.items():
            old=previous[case][arm]
            assert row['graph']==old['graph'] and row['source_sha']==old['source_sha']
            assert row['runs']==old['runs'] and row['placement']==old['placement']
            assert (row['issued'],row['selected'],row['saved'])==(old['issued'],old['selected'],old['immediate_bytes'])
            assert row['opportunity_sha']==sha([table[i] for i in old['actions']])
            assert row['curve'][-1][5]==old['final_charge'][0]
            assert row['probes']==row['runs']-1 and row['probe_ns']>0 and row['stride']==1
            assert row['static_start'][2]==row['static_end'][2]==row['terminal'][2]
            assert row['after_export']==row['terminal']
            library=sum(n for k,n in row['program_fields'] if k.startswith(('ownership.','composition.')) or k=='artifact.ownership_fragments')
            assert library==row['terminal'][2] and 0<library<row['terminal'][1]
            if arm.endswith('retrained'):
                assert row['rejected']=={'epoch':True,'selected':True}
            else:assert not row['selected']
        means[case]=analyze(rows)
    assert means==load(folder/'summary.json')
    pilot=load(folder/'pilot.json')
    assert pilot['runs']>0 and pilot['probes']>0 and pilot['probe_ns']>0
    assert all(pilot[k]==load(folder/'gemm-bias-relu.json')['pooled/keep'][k] for k in ('graph','source_sha','runs'))
    return means


if __name__=='__main__':
    print('Verified every settled source Run, isolated heap releases, charged phases and native owner actions across',len(verify()),'workloads')
