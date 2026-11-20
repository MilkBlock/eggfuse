"""Check the archived full schedules, physical witnesses, held-out provenance and timing sample counts."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


def verify():
    catalog = read('pair-catalog.json')
    assert catalog['pairs'] == [[509,510]]
    assert len(catalog['training']['(509, 510)']) == 4
    principal = read('siblings.json')
    assert len(principal) == 8
    for key, arms in principal.items():
        source = arms['independent']['guarded']['commit_identity']
        for name, v in arms.items():
            assert v['actual'] == v['rhs'] and v['source_aligned'] and v['graph_exact']
            assert 100*v['direct_cells'] >= 98*v['fresh_cells']
            if name != 'stale':
                assert len(v['ms']) == len(v['request_ms']) == 8
            if name == 'base':
                continue
            p = v['guarded']
            assert p['commit_identity'] == source
            if name in ('verified','raw'):
                assert p['reused_sibling_runs'] and p['shared_raw_tuples']
            if name == 'verified':
                assert p['comparisons'] == p['lt'] + p['gt'] + p['eq']
                assert p['cross_stage'] and p['committed'] >= p['cross_stage']
            if name == 'stale':
                assert p['snapshot_misses'] and not p['reused_sibling_runs']
    larger = read('larger-holdouts.json')
    assert len(larger) == 4
    for key, arms in larger.items():
        for name, v in arms.items():
            assert len(v['ms']) == 6
            if name == 'vanilla':
                continue
            assert v['aligned'] and all(v['checks'].values())
            assert v['rhs'] == v['neural_rhs'] == v['applied'] == arms['vanilla']['rhs']
            assert 100*v['direct_cells'] >= 98*v['fresh']
        assert arms['both']['subtuple_children'] == arms['subtuple']['subtuple_children'] > 0
        assert arms['both']['cross_stage_shared'] == arms['sibling']['cross_stage_shared'] > 0
    print('Checked the frozen complementary guards on four source programs and two new workload families.')


if __name__ == '__main__':
    verify()
