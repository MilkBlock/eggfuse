#!/usr/bin/env python3
"""Check retained Cell catalog compression and saved ordinary executions."""
import argparse
import json
from pathlib import Path
from check_links import load, sha
from check_mixed_outputs import pair


def check(args):
    before,after=load(args.before),load(args.after)
    field={'paths':'storage','dispatch':'dispatch','exports':'export_storage','captures':'capture_storage','transitions':'transition_storage','completion':'completion_storage'}[args.mode]
    a,b=before.pop(field),after.pop(field)
    if args.mode in ('transitions','completion'):
        # The two censuses overlap in the state array: validate and charge it once.
        for report, stats in ((before,a),(after,b)):
            assert report['capture_storage'].pop('node_array_bytes')==stats['node_array_bytes']
            if args.mode=='completion':
                assert report['transition_storage'].pop('node_array_bytes')==stats['node_array_bytes']
    assert before==after, 'expanded paths and complete state contracts must match'
    if args.mode=='completion':
        assert a['states']==b['states'] and a['lowered_reads']==b['lowered_reads']
        fields=('node_array_bytes','program_owner_bytes','read_payload_bytes')
    elif args.mode=='transitions':
        assert a['states']==b['states']
        fields=('node_array_bytes','transition_payload_bytes','transition_owner_bytes')
    elif args.mode=='captures':
        assert a['captures']==b['captures'], 'capture programs must retain actual rule/slot identities'
        assert a['states']==b['states'] and b['node_capacity']==b['states']
        fields=('node_array_bytes','capture_payload_bytes','capture_owner_bytes')
    elif args.mode=='exports':
        assert a['interfaces']==b['interfaces'], 'all exported slot identities must match'
        fields=('directory_bytes','slot_bytes')
    elif args.mode=='dispatch':
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
    baseline_commit={'paths':'0126e0cd','dispatch':'9e0bac8a','exports':'d75aed32','captures':'a183c982','transitions':'bd421908','completion':'08dd9ac6'}[args.mode]
    probe={'paths':'catalog','dispatch':'dispatch','exports':'export','captures':'capture','transitions':'transition','completion':'completion'}[args.mode]
    return dict(scope='standalone Cell CPU ordinary loaded catalog; retained '+args.mode+' structures',
        baseline_commit=args.baseline_commit or baseline_commit,program=before['program'],exact_entries_and_state_contracts_equal=True,
        baseline=a,candidate=b,baseline_bytes=old,candidate_bytes=new,bytes_saved=old-new,
        fractional_reduction=1-new/old,runtime=runtime,semantic_acceptance='pass',
        binaries={k:sha(getattr(args,k)) for k in ('baseline','candidate')},
        inspections={k:sha(getattr(args,k)) for k in ('before','after')},
        baseline_probe_patch_sha256=None if args.baseline_commit else sha(Path(__file__).with_name(probe+'-storage-probe.patch')),
        limits=('Counts node array once, unique completion programs with two-word Rc headers, and read-array '
               'capacity. Node array overlaps other censuses; totals are not additive. Excludes allocator '
               'rounding and unrelated arrays. No speed or takeover claim.' if args.mode=='completion' else 'Counts node array once, unique transition payloads and two-word Rc owners. Node array '
               'overlaps capture census; do not add those totals. Excludes other node-owned arrays and '
               'allocator rounding. No speed or takeover claim.' if args.mode=='transitions' else 'Counts node-array capacity, unique capture payloads and two-word Rc owners. Excludes other '
               'node-owned arrays, allocator rounding and switch header. No speed or new takeover claim.' if args.mode=='captures' else 'Counts export directory and slot arrays including baseline capacity. Excludes allocator overhead, '
               'switch header and other switch data. No speed or new cross-stage takeover claim.' if args.mode=='exports' else 'Counts rule-row directory, nullable leaf arrays and former duplicate lookup entry payloads. '
               'Excludes BTree node spare slots/links, allocator rounding, switch header and other switch data. '
               'No speed or new cross-stage takeover claim.' if args.mode=='dispatch' else 'Counts unit-array capacity, path-array capacities and former duplicate lookup keys/payloads. '
               'Excludes BTree node spare slots/links, allocator rounding, catalog header, other indexes, '
               'state switch and JSON artifact storage. No speed or new cross-stage takeover claim.'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('before','after','root','program','baseline','candidate','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--mode',choices=('paths','dispatch','exports','captures','transitions','completion'),default='paths')
    parser.add_argument('--baseline-commit',help='Baseline with built-in census; no probe patch applied')
    args=parser.parse_args()
    args.output.write_text(json.dumps(check(args),indent=2)+'\n')
