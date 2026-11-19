"""Summarize both panels from saved evaluation and independent Rust/CPU replay."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(root, output):
    files = [root / name for name in ('results.json', 'cpu-replay.json', 'repeat-timing.json')]
    run, audit, repeat = [json.loads(path.read_text()) for path in files]
    if audit['results_sha256'] != digest(files[0]) or repeat['reference_sha256'] != digest(files[0]):
        raise ValueError('Reports do not describe the same evaluation')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'metrics.tsv').open('w') as handle:
        writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
        writer.writerow(('panel','schedule','graphs','complete','rust_exact','private_wave0',
                         'private_wave1','private_wave2','private_finish','early_fires',
                         'c_delay_ticks','v_delay_ticks','unrelated_v_idle_ticks','drain','median_ms'))
        for split, lanes in run['panels'].items():
            for name, panel in lanes.items():
                checked = audit['panels'][split][name]
                totals = panel['totals']
                assert checked['totals'] == totals and checked['complete'] == panel['complete_graphs']
                writer.writerow((split,name,panel['graphs'],checked['complete'],
                                 checked['source_ordinal_hashes']['all_cpu_run_hashes_and_finish_witnesses_exact'],
                                 *(r['private_rhs_evaluations'] for r in panel['per_run']),
                                 totals['early_fires'],totals['c_valid_private_delay_ticks'],
                                 totals['v_valid_private_delay_ticks'],totals['unrelated_v_ready_idle_ticks'],
                                 totals['drained_at_finish'],round(run['timings'][split][name]['median_ms'],5)))
    record = dict(files_sha256={path.name: digest(path) for path in files},
                  plan_sha256=run['plan_sha256'], rust_distinct_sources=audit['rust_distinct_sources'],
                  trace_sha256=audit['trace_sha256'], round_medians_ms=repeat['round_medians_ms'],
                  paired_difference_per_round_ms=repeat['paired_difference_per_round_ms'],
                  pooled_paired_difference_ms=repeat['paired_difference_ms'])
    (output / 'evidence.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    summarize(args.root,args.output)
