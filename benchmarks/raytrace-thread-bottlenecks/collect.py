#!/usr/bin/env python3
"""Retain bounded text evidence and validate the sample tree's count accounting."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil


def sample_threads(path, expected_threads=5):
    graph = path.read_text().split('Call graph:\n', 1)[1].split('Total number in stack', 1)[0]
    roots, stack = [], []
    for line in graph.splitlines():
        match = re.match(r'([ +!|:`]*)(\d+) (.*)', line)
        if not match:
            continue
        depth, count = len(match[1]), int(match[2])
        symbol = re.sub(r'::h[0-9a-f]{16}$', '', match[3].split('  (in ', 1)[0])
        node = {'depth': depth, 'count': count, 'symbol': symbol, 'children': []}
        while stack and stack[-1]['depth'] >= depth:
            stack.pop()
        (stack[-1]['children'] if stack else roots).append(node)
        stack.append(node)
    result = []
    for root in roots:
        inclusive, own, inference_inclusive = Counter(), Counter(), Counter()

        def walk(node, ancestors=()):
            symbol, count = node['symbol'], node['count']
            children = sum(c['count'] for c in node['children'])
            assert count >= children, (symbol, count, children)
            if symbol not in ancestors:
                inclusive[symbol] += count
                if 'eggfuse_cell_runtime::executor::Executor::execute_until' in ancestors + (symbol,):
                    inference_inclusive[symbol] += count
            own[symbol] += count - children
            for child in node['children']:
                walk(child, ancestors + (symbol,))

        walk(root)
        assert sum(own.values()) == root['count']
        result.append({'thread': root['symbol'], 'samples': root['count'],
                       'inclusive': dict(inclusive.most_common()),
                       'inference_inclusive': dict(inference_inclusive.most_common()),
                       'own': dict((k, v) for k, v in own.most_common() if v)})
    assert len(result) == expected_threads and all(x['samples'] > 0 for x in result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/collect.py'))
    base['collect'](args.root / 'timing', args.output / 'summary.json')
    samples = json.loads((args.root / 'timing/samples.json').read_text())
    diagnostic = json.loads((args.root / 'profile/diagnostic.json').read_text())
    assert {k: diagnostic[k] for k in samples['semantic_reference']} == samples['semantic_reference']
    for key in ('runtime_sha256', 'program_file_sha256'):
        assert diagnostic[key] == samples['lanes']['overlap4'][key]
    stacks = args.root / 'profile/stacks.txt'
    assert hashlib.sha256(stacks.read_bytes()).hexdigest() == diagnostic['sample']['stacks_sha256']
    threads = sample_threads(stacks)
    main_thread, *workers = threads
    inference = main_thread['inclusive']['eggfuse_cell_runtime::executor::Executor::execute_until']
    selected = ['Executor::matches', 'lookup_port_key', 'owned_candidates',
                'publish_finished_tables', 'repair_selected', 'complete_port_read_batch',
                'overlap_completion_tasks', 'root_counted', 'Once::wait']
    profile = {k: diagnostic[k] for k in ('scope', 'lane', 'args', 'runs', 'state_sha256',
               'schedule_sha256', 'runtime_sha256', 'program_file_sha256', 'sample')}
    profile['main_inference_stack_samples'] = inference
    profile['main_selected_inclusive'] = {
        key: sum(n for s, n in main_thread['inference_inclusive'].items() if s.endswith(key)) for key in selected}
    profile['main_selected_limits'] = 'Inclusive counts overlap and must not be summed. Selected counts are restricted to execute_until ancestors; optimized inlining limits attribution. Whole-window thread counts include a short reporting tail.'
    profile['worker_parked'] = [
        {'thread': w['thread'], 'samples': w['samples'], 'condition_wait_samples': w['inclusive'].get('__psynch_cvwait', 0),
         'condition_wait_fraction': w['inclusive'].get('__psynch_cvwait', 0) / w['samples']} for w in workers]
    profile['threads'] = threads
    (args.output / 'profile.json').write_text(json.dumps(profile, indent=2) + '\n')
    for source, name in [(args.root / 'timing/samples.json', 'samples.json'),
                         (args.root / 'provenance.json', 'provenance.json'),
                         (stacks, 'stacks.txt')]:
        shutil.copyfile(source, args.output / name)
    print(json.dumps({'main': profile['main_selected_inclusive'], 'workers': profile['worker_parked']}, indent=2))


if __name__ == '__main__':
    main()
