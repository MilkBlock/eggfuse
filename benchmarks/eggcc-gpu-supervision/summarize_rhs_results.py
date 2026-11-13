"""Summarize actual RHS observation coverage; never certify token takeover."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from collect_observed_corpus import read_bytes


def summarize(trace):
    if trace['schema'] != 'eggcc-gpu-supervision-rhs-trace/v1':
        raise ValueError('not an actual RHS trace')
    for key in ('strict_run_graphs_equal', 'strict_audit_reference_equal', 'run_control_counts_equal'):
        if trace.get(key) is not True:
            raise ValueError('missing reference audit: '+key)
    counts = Counter()
    missing = Counter()
    for run in trace['runs']:
        for binding in run['audit']['bindings']:
            counts['applications'] += 1
            rhs = binding['rhs']
            counts['completed_applications'] += int(rhs['completed'])
            inputs = {v['slot'] for v in binding['values']}
            for slot in rhs['slots']:
                counts['slot_reads'] += 1
                if 'unavailable' in slot:
                    missing[slot['unavailable']] += 1
                    continue
                counts['available_slots'] += 1
                counts['rhs_only_slots'] += int(slot['slot'] not in inputs)
                if 'eq_port' in slot:
                    counts['eq_slots'] += 1
                    counts['rhs_only_eq_slots'] += int(slot['slot'] not in inputs)
                    p = slot['eq_port']
                    counts['eq_slots_changed_during_completion'] += int(p['at_rhs'] != p['after_run'])
    return dict(schema='actual-rhs-capture-summary/v1',program_sha256=trace['program_sha256'],
                runs=len(trace['steps']), counts=dict(counts), unavailable=dict(missing),
                unavailable_slot_fraction=sum(missing.values()) / max(1, counts['slot_reads']),
                timing={k:v for k,v in trace.items() if k.endswith('_seconds')},
                strict_run_graphs_equal=True, strict_final_graph_equal=True,
                scope='actual CPU execution observation, not GPU inference or native egglog acceptance',
                limitations=['Slot Eq identity is not a constructor ownership or retirement certificate',
                             'No proven producer-consumer causal links or GPU takeover',
                             'Callback timing excludes slot-read collection; observed execution includes it',
                             'Debug audit timing is not a performance benchmark'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('trace',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();raw=read_bytes(args.trace)
    report=summarize(json.loads(raw));report['trace_sha256']=hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['counts']))

if __name__=='__main__':main()
