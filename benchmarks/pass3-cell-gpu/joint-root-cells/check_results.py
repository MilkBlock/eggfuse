"""Validate actual allocator-consumed root recipes independently from source-template correspondence."""
import json
from pathlib import Path


def check(root):
    read=lambda f:json.loads((root/f).read_bytes())
    result=read('results.json');proof=read('physical-proof.json');both=read('combined-forbid.json');timing=read('timings.json')
    assert len(result)==16 and set(result)==set(proof)==set(both)==set(timing)
    for key,arms in result.items():
        r=arms['use'];e=proof[key];c=both[key]
        assert r['source_exact'] and r['root_consumed']==r['neural_rhs']
        assert r['direct_roots']==e['distinct_root_ids'] and r['direct_children']==e['distinct_child_ids']
        assert r['direct_distinct']==r['direct_roots']+r['direct_children']==r['fresh']-len(e['uncovered_ids'])
        assert 100*r['direct_distinct']>=98*r['fresh'] and 100*r['neural_rhs']>=98*r['rhs']
        assert sum(e['issued'])>=e['verified']>=r['root_consumed'] and e['wire_bytes']>0
        assert e['examples'].keys()=={'single','multi'}
        for arm in ('wrong-template','wrong-port','withhold','shadow'):
            v=arms[arm];assert v['source_exact'] and v['direct_roots']==0
            assert v['allocation_sha']==r['allocation_sha'] and v['root_proposal_hash']==r['root_proposal_hash']
        assert arms['withhold/no-fallback']['first_uncompleted_run']==1
        assert c['wrong-template']['first_uncompleted_run']==c['wrong-port']['first_uncompleted_run']==1
        if key.endswith('/certified'):
            assert r['neural_rhs']==r['rhs'] and arms['use/no-fallback']['source_exact']
        else:assert arms['use/no-fallback']['first_uncompleted_run']>1
        assert all(len(v['inference_ms'])==len(v['request_ms'])==8 for v in timing[key].values())
    print('Verified allocator-driven root and nested union of distinct physical ids in 16 full Pass 3 conditions.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
