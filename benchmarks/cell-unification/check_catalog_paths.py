#!/usr/bin/env python3
"""Check retained Cell path compression and saved ordinary executions."""
import argparse
import json
from pathlib import Path
from check_links import load, sha
from check_mixed_outputs import pair


def check(args):
    before,after=load(args.before),load(args.after)
    field='dispatch' if args.mode=='dispatch' else 'storage'
    a,b=before.pop(field),after.pop(field)
    assert before==after, 'expanded paths and complete state contracts must match'
    if args.mode=='dispatch':
        assert a['rule_slots']==b['rule_slots']
        assert b['duplicate_lookup_entry_bytes']==0
        fields=('row_directory_bytes','rule_slot_bytes','root_slot_bytes','duplicate_lookup_entry_bytes')
    else:
        assert a['units']==b['units'] and a['unit_capacity']==b['unit_capacity']
        assert b['lookup_key_bytes']==b['lookup_payload_bytes']==0
        fields=('unit_array_bytes','path_payload_bytes','lookup_key_bytes','lookup_payload_bytes')
    old,new=(sum(s[k] for k in fields) for s in (a,b))
    assert new<old
    runtime=pair(args.root,('baseline','candidate'),args.program,allowed=set(),charged=set())
    acceptance=load(args.root/'semantic-acceptance.json')
    assert acceptance['status']=='pass'
    assert acceptance['input_sha256']['cpu_values']==runtime['ordered_hashes']['state.json']
    return dict(scope='standalone Cell CPU ordinary loaded catalog; retained '+args.mode+' structures',
        baseline_commit=args.baseline_commit or ('9e0bac8a' if args.mode=='dispatch' else '0126e0cd'),program=before['program'],exact_entries_and_state_contracts_equal=True,
        baseline=a,candidate=b,baseline_bytes=old,candidate_bytes=new,bytes_saved=old-new,
        fractional_reduction=1-new/old,runtime=runtime,semantic_acceptance='pass',
        binaries={k:sha(getattr(args,k)) for k in ('baseline','candidate')},
        inspections={k:sha(getattr(args,k)) for k in ('before','after')},
        baseline_probe_patch_sha256=None if args.baseline_commit else sha(Path(__file__).with_name(('dispatch' if args.mode=='dispatch' else 'catalog')+'-storage-probe.patch')),
        limits=('Counts rule-row directory, nullable leaf arrays and former duplicate lookup entry payloads. '
               'Excludes BTree node spare slots/links, allocator rounding, switch header and other switch data. '
               'No speed or new cross-stage takeover claim.' if args.mode=='dispatch' else 'Counts unit-array capacity, path-array capacities and former duplicate lookup keys/payloads. '
               'Excludes BTree node spare slots/links, allocator rounding, catalog header, other indexes, '
               'state switch and JSON artifact storage. No speed or new cross-stage takeover claim.'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('before','after','root','program','baseline','candidate','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--mode',choices=('paths','dispatch'),default='paths')
    parser.add_argument('--baseline-commit',help='Baseline with built-in census; no probe patch applied')
    args=parser.parse_args()
    args.output.write_text(json.dumps(check(args),indent=2)+'\n')
