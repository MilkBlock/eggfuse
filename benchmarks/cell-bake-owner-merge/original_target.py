"""Anchor the 30% budget to the original source, not a different pass3 run."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    data=path.read_bytes()
    return json.loads(data),hashlib.sha256(data).hexdigest()


def summarize(baseline_path, memory_path, checked_path):
    baseline, old_sha=read(baseline_path)
    memory, memory_sha=read(memory_path)
    checked, checked_sha=read(checked_path)
    for key in ('program_sha256','runs'):
        if not baseline[key]==memory[key]==checked[key]:
            raise ValueError('original source mismatch: '+key)
    if (checked.get('completed_owners') is not True or
            checked.get('every_run_graph_and_ordered_audits_equal') is not True or
            len(checked.get('run_checks',[]))!=checked['runs']):
        raise ValueError('missing complete source Run comparison')
    original=baseline['graph_owned_heap_requested_before']
    current=memory['graph_owned_teardown_bytes']
    budget=original*3//10
    return dict(scope='original-source cumulative retained Graph comparison; not a speed result or native semantic proof',
        program_sha256=memory['program_sha256'],runs=memory['runs'],
        inputs=dict(baseline_sha256=old_sha,memory_sha256=memory_sha,checked_sha256=checked_sha),
        original_graph_bytes=original,current_graph_bytes=current,
        fraction_of_original=current/original,target_graph_bytes=budget,
        remaining_bytes_to_target=max(0,current-budget),
        current_same_binary_control_bytes=checked['graph_owned_heap_requested_before'],
        current_same_binary_candidate_bytes=checked['graph_owned_heap_requested_after'],
        all_run_graph_and_ordered_audits_equal=True,
        graph_fields=memory['graph_fields'],
        limitations=['The original baseline was a working-tree observation, not a pristine isolated revision.',
            'Final Graph requested heap excludes Program, Executor caches and allocator overhead.',
            'This does not prove a Graph-only execution peak or a native final-state contract.',
            'The 30% target and fast saturated-stage RHS generation are separate unfinished requirements.'])


if __name__=='__main__':
    Path(sys.argv[4]).write_text(json.dumps(summarize(*(Path(p) for p in sys.argv[1:4])),indent=2)+'\n')
