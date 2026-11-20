"""Check deferred read accounting and source/receipt equivalence using archived real executions."""
import argparse
import json
from pathlib import Path
from statistics import median


def verify(source):
    cases = json.loads(source.read_bytes())
    for name, variants in cases.items():
        gold = variants['vanilla']
        base = variants['immediate']
        assert base['requests']['flushes'] == 0
        for arm, v in variants.items():
            assert len(v['ms']) >= 4 and median(v['ms']) == v['median_ms']
            if arm == 'vanilla':
                continue
            assert v['aligned'] and set(v['checks']) == {'rhs','writes','resumes','state_sha','schedule','runs','unions'}
            assert all(v['checks'].values()) and v['rhs'] == v['neural_rhs'] == gold['rhs']
            assert 100*v['direct_cells'] >= 98*v['fresh']
            for field in ('raw','commits','physical','multi','children','cells','emitted','root_allocated','applied','request_digest'):
                assert v[field] == base[field], (name,arm,field)
            if arm == 'immediate':
                continue
            width = int(arm.rsplit('-',1)[1])
            r = v['requests']
            assert 0 < r['peak_lanes'] <= width and r['flushes'] <= (r['lanes'] if arm.startswith('stream') else r['raw_batches'])
            assert r['lanes'] >= r['survivors'] and r['reads'] + r['evaluations'] > 0
            assert v['point_reads'] + r['reused_rows'] == base['point_reads']
            assert v['primitive_evals'] + r['reused_scalars'] == base['primitive_evals']
            assert r['parent_reads'] + r['reused_parents'] == variants['transaction-1']['requests']['parent_reads']
            assert r['collect_ns'] == r['max_collect_ns'] == r['execute_ns'] == 0
            assert v['diagnostic_ns']['execute_ns'] > 0 and v['diagnostic_ns']['collect_ns'] >= v['diagnostic_ns']['max_collect_ns']
            if arm.startswith('transaction-'):
                assert r['reused_rows'] == r['reused_scalars'] == r['reused_parents'] == 0
            if arm == 'reads-32':
                assert r['reused_scalars'] == 0
            if arm == 'stream-8':
                for field in ('parent_reads','reads','evaluations','reused_parents','reused_rows','reused_scalars','lanes','survivors','raw_batches'):
                    assert r[field] == variants['parents-8']['requests'][field]
                assert r['peak_lanes'] == 1 and r['deferred_lane_pairs'] == 0
            if width == 1:
                assert r['deferred_lane_pairs'] == 0
    return cases


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('results', type=Path, nargs='+')
    for path in p.parse_args().results:
        print(f'{len(verify(path))} verified workload/seed pairs in {path.name}')
