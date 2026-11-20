"""Verify recorded native event attribution and the crossed curriculum/reward experiment."""
import json
from pathlib import Path
from statistics import median
from feature_support import counts
from synthetic import check


def verify(folder):
    read=lambda n:json.loads((folder/n).read_bytes())
    check()
    train=read('training-events.json');policy=read('policies.json');results=read('results.json')
    assert set(train)==set(policy['train_cases'])=={'affine-twins','clamped-ramp','segmented-prefix','window-laplacian'}
    allrows=[r for d in train.values() for r in d['charges']]
    assert counts(allrows)==read('feature-support.json')['pooled']
    assert policy['native_events']==len(allrows)==689 and policy['native_child_wins']==sum(d['children'] for d in train.values())==295
    assert policy['updates']==120 and policy['warm']==80
    for case,d in train.items():
        b=d['on_boundary'];enc,fresh,won,owned=map(sum,zip(*(r['counts'] for r in d['charges'])))
        assert enc-fresh==b[2]-b[3] and fresh==b[6]==b[8] and won==d['children'] and owned<=b[1]
        assert len({x['generation'] for x in d['charges']})==len(d['charges'])
    names={f'{source}-{credit}' for source in ('real','synthetic') for credit in ('prior','offer','settled','work','charged')}
    assert set(results)=={f'{case}/{seed}' for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax') for seed in (1703,1709)}
    for key,v in results.items():
        case,seed=key.split('/');assert case not in train and set(v)==names|{'all','leaf'}
        assert v['all']['selected']==v['all']['opportunities'] and v['leaf']['selected']==0
        for arm,row in v.items():
            if arm in names:
                gate=policy['policies'][seed+'-'+arm]['gate']
                assert len(gate['weights'])==8 and gate['threshold']==0.
            assert row['endpoint_digest']==v['leaf']['endpoint_digest']
            assert row['direct']*100>=98*row['fresh'] and row['rhs']==v['leaf']['rhs']
            assert 0<=row['completed']<=min(row['selected'],row['verified_child_total'])
            assert row['net_operations']==row['skipped_entries']+row['saved_seals']+row['saved_packets']-row['header_scans']
            assert len(row['ms'])==6 and median(row['ms'])==row['median_ms']
    from compare import summarize
    assert summarize(results)==read('comparison.json')
    spec=read('scarce-policies.json')
    assert spec['train_cases']==['affine-twins'] and spec['native_events']==96 and spec['native_child_wins']==41
    assert summarize(read('scarce-results.json'))==read('scarce-comparison.json')
    for fname,expected in [('scarce-results.json',4),('delta-transfer.json',4),('larger.json',1)]:
        other=read(fname);assert len(other)==expected
        for case,group in other.items():
            for arm,row in group.items():
                assert len(row['ms'])==6 and median(row['ms'])==row['median_ms']
                if arm=='vanilla':continue
                assert row['endpoint_digest']==group['leaf']['endpoint_digest']
                assert row['direct']*100>=98*row['fresh'] and row['completed']<=row['verified_child_total']
                assert row['net_operations']==row['skipped_entries']+row['saved_packets']+row['saved_seals']-row['header_scans']
                if fname=='delta-transfer.json':
                    assert len(row['delta_maintenance'])==5
    return len(results)


if __name__=='__main__':
    print('Verified frozen gates, source provenance, operation counts and timings across',verify(Path(__file__).parent),'workload/seed pairs.')
