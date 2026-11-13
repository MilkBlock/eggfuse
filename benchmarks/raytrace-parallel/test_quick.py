#!/usr/bin/env python3
"""Exercise concurrency detection and retention without timing Cell workloads."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('quick', Path(__file__).with_name('quick.py'))
quick = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quick)


class GuardTests(unittest.TestCase):
    def test_timing_api_also_queues_the_whole_trial(self):
        args = tuple(Path(x) for x in ('before', 'after', 'output', 'result.json'))
        with patch.object(quick.jobs, 'current_lease', return_value=None), \
                patch.object(quick.jobs, 'run_command', return_value=0) as launch:
            quick.run(*args)
        self.assertEqual(launch.call_args.kwargs, {'kind': 'timing'})
        self.assertEqual(launch.call_args.args[1][-4:], list(map(str, args)))

    def test_compute_or_unguarded_lease_cannot_start_a_trial(self):
        for lease in ({'kind':'compute','guard':'known'}, {'kind':'timing','guard':'none'}):
            with patch.object(quick.jobs, 'current_lease', return_value=lease):
                with self.assertRaisesRegex(RuntimeError, 'Timing requires'):
                    quick.run(*(Path(x) for x in ('before','after','output','result.json')))

    def test_full_executable_names_with_spaces_and_numeric_benchmark_links(self):
        raw = ('1 0.0 /Users/name with spaces/.rustup/toolchains/stable/bin/cargo\n'
               '2 80.0 /Users/name/.rustup/toolchains/stable/bin/rustc\n'
               '3 100.0 target/debug/examples/batch_cell_learning\n'
               '4 50.0 /tmp/bench/group-0000/binaries/0000\n'
               '5 30.0 /System/Library/WindowServer\n'
               '6 100.0 /tmp/target/debug/deps/query_workers-aabbcc\n')
        with patch.object(quick.subprocess, 'check_output', return_value=raw) as call:
            observation = quick.processes()
        self.assertEqual(call.call_args.args[0], ['ps', '-axww', '-o', 'pid=,pcpu=,comm='])
        self.assertEqual(len(observation['compilers']), 2)
        self.assertEqual(len(observation['workloads']), 3)

    def test_guard_preserves_evidence_and_rejects_other_runtime(self):
        observation = {'utc': 'test', 'compilers': [], 'workloads': ['3 0.0 target/debug/examples/other'],
                       'processes': '3 0.0 target/debug/examples/other\n5 0.0 /usr/bin/idle'}
        with tempfile.TemporaryDirectory() as directory, patch.object(quick, 'processes', return_value=observation):
            output = Path(directory)
            result = {'observations': []}
            with self.assertRaisesRegex(RuntimeError, 'Concurrent compiler/runtime'):
                quick.guard(result, output, 'after-sample', 'control', 'ray', 0)
            stored = json.loads((output / 'progress.json').read_text())
            self.assertEqual(stored['measurement_status'], 'interrupted-by-concurrent-work')
            self.assertEqual(stored['observations'][0]['workloads'], observation['workloads'])
            self.assertNotIn('idle', stored['observations'][0]['processes'])

    def test_interruption_after_sample_retains_it_and_stops_later_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'fake-runtime'
            runtime.write_text('''#!/usr/bin/env python3
import json,sys
from pathlib import Path
p=Path(sys.argv[sys.argv.index('--output')+1]);p.mkdir()
step={k:0 for k in ('ordinal','ruleset','path','iterations','epoch','logical_matches','executed_bindings','changed')}
step['phases']={}
(p/'report.json').write_text(json.dumps({'status':'complete','steps':[step],'stats':{},'inference_seconds':0}))
(p/'state.json').write_text('{}')
''')
            runtime.chmod(0o755)
            program = root / 'program.json'
            program.write_text('{}')
            output = root / 'results'
            phases = []

            def boundary(phase, lane, iteration):
                phases.append((phase, lane, iteration))
                if phase == 'after-sample':
                    raise RuntimeError('external runtime appeared')

            with self.assertRaisesRegex(RuntimeError, 'external runtime appeared'):
                quick.timer['measure']({'lanes': {'control': {'runtime': str(runtime), 'program': str(program)}}},
                    output, 2, 1, 10, sample_boundary=boundary)
            stored = json.loads((output / 'samples.json').read_text())
            self.assertEqual(len(stored['lanes']['control']['warmup_samples']), 1)
            self.assertEqual(stored['lanes']['control']['samples'], [])
            self.assertEqual(phases, [('before-sample', 'control', -1), ('after-sample', 'control', -1)])


if __name__ == '__main__':
    unittest.main()
