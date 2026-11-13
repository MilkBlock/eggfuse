#!/usr/bin/env python3
"""Isolated scheduler lifecycle tests; no CPU benchmark measurements."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('local_jobs.py').resolve()
spec = importlib.util.spec_from_file_location('local_jobs', SCRIPT)
jobs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jobs)


def eventually(predicate, timeout=10):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError('Condition did not become true')


class QueueTests(unittest.TestCase):
    def setUp(self):
        # Short paths also exercise macOS's Unix-domain socket path limit.
        self.temp = tempfile.TemporaryDirectory(prefix='ej-', dir='/tmp')
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / 'q'
        self.log = (self.root / 'daemon.log').open('w')
        self.daemons = []
        self.start()

    def start(self):
        process = subprocess.Popen([sys.executable, str(SCRIPT), '--state-dir', str(self.state),
            'serve', '--guard', 'none'], stdout=self.log, stderr=self.log)
        self.daemons.append(process)
        def ready():
            try:
                return jobs.rpc(self.state, 'ping')['pid'] == process.pid
            except (OSError, RuntimeError):
                return False
        eventually(ready)

    def tearDown(self):
        try:
            state = jobs.rpc(self.state, 'status')
            for job in state['jobs']:
                if job['status'] not in jobs.TERMINAL:
                    jobs.rpc(self.state, 'cancel', id=job['id'])
                    jobs.rpc(self.state, 'wait', id=job['id'])
            jobs.rpc(self.state, 'stop')
        except (OSError, RuntimeError):
            pass
        for p in self.daemons:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        self.log.close()
        self.temp.cleanup()

    def submit(self, code, kind='compute', cwd=None, env=None):
        return jobs.rpc(self.state, 'submit', argv=[sys.executable, '-c', code],
            cwd=str(cwd or self.root), env=dict(os.environ, **(env or {})), kind=kind, quiet=0)

    def running(self, identity):
        return next(j for j in jobs.rpc(self.state, 'status')['jobs'] if j['id'] == identity)['status'] == 'running'

    def test_fifo_across_worktrees_preserves_cwd_env_and_failure_exit(self):
        a, b = self.root / 'a', self.root / 'b'
        a.mkdir(); b.mkdir()
        first = self.submit("import time; time.sleep(.2); print('first')", kind='timing', cwd=a)
        second = self.submit("import os; print(os.getcwd()); print(os.environ['ONLY_THIS_JOB']); raise SystemExit(7)",
                             cwd=b, env={'ONLY_THIS_JOB': 'private-test-value'})
        third = self.submit("print('third')")
        done = [jobs.rpc(self.state, 'wait', id=j['id']) for j in (first, second, third)]
        self.assertLessEqual(done[0]['finished'], done[1]['started'])
        self.assertLessEqual(done[1]['finished'], done[2]['started'])
        self.assertEqual([j['exit_code'] for j in done], [0, 7, 0])
        self.assertIn(str(b), Path(done[1]['log']).read_text())
        self.assertIn('private-test-value', Path(done[1]['log']).read_text())
        self.assertNotIn('private-test-value', (self.state / 'jobs.json').read_text())
        self.assertNotIn('EGGFUSE_JOB_TOKEN', (self.state / 'jobs.json').read_text())

    def test_cancel_queued_does_not_run_it_and_cancel_running_releases_queue(self):
        first = self.submit('import time; time.sleep(60)')
        eventually(lambda: self.running(first['id']))
        marker = self.root / 'never'
        second = self.submit(f'from pathlib import Path; Path({str(marker)!r}).touch()')
        jobs.rpc(self.state, 'cancel', id=second['id'])
        self.assertEqual(jobs.rpc(self.state, 'wait', id=second['id'])['status'], 'cancelled')
        jobs.rpc(self.state, 'cancel', id=first['id'])
        self.assertEqual(jobs.rpc(self.state, 'wait', id=first['id'])['exit_code'], 130)
        self.assertFalse(marker.exists())
        third = self.submit('print(3)')
        self.assertEqual(jobs.rpc(self.state, 'wait', id=third['id'])['exit_code'], 0)

    def test_nested_command_reuses_lease_and_cannot_upgrade_compute_to_timing(self):
        cmd = [sys.executable, str(SCRIPT), 'run', '--', sys.executable, '-c', 'print("nested")']
        first = self.submit(f'import subprocess; raise SystemExit(subprocess.call({cmd!r}))', kind='timing')
        done = jobs.rpc(self.state, 'wait', id=first['id'])
        self.assertEqual(done['exit_code'], 0)
        self.assertIn('nested', Path(done['log']).read_text())
        cmd[3:3] = ['--kind', 'timing']
        second = self.submit(f'import subprocess; raise SystemExit(subprocess.call({cmd!r}))')
        done = jobs.rpc(self.state, 'wait', id=second['id'])
        self.assertEqual(done['exit_code'], 125)
        self.assertIn('whole pipeline', Path(done['log']).read_text())
        self.assertEqual(len(jobs.rpc(self.state, 'status')['jobs']), 2)

    def test_daemon_crash_kills_owned_group_and_does_not_replay_queued_work(self):
        first = self.submit('import time; time.sleep(60)')
        eventually(lambda: self.running(first['id']))
        state = jobs.rpc(self.state, 'status')
        pid = state['jobs'][0]['pid']
        second = self.submit('raise SystemExit(99)')
        self.daemons[-1].kill()
        self.daemons[-1].wait()
        eventually(lambda: not jobs.group_members(pid))
        self.start()
        state = jobs.rpc(self.state, 'status')
        self.assertEqual([j['status'] for j in state['jobs']], ['interrupted', 'interrupted'])
        self.assertFalse(Path(second['log']).exists())
        third = self.submit('print("recovered")')
        self.assertEqual(jobs.rpc(self.state, 'wait', id=third['id'])['exit_code'], 0)

    def test_background_descendants_remain_inside_the_reservation(self):
        marker = self.root / 'child-done'
        child = f'import time; from pathlib import Path; time.sleep(.3); Path({str(marker)!r}).touch()'
        first = self.submit(f'import subprocess,sys; subprocess.Popen([sys.executable,"-c",{child!r}])')
        second = self.submit(f'from pathlib import Path; assert Path({str(marker)!r}).exists()')
        a, b = [jobs.rpc(self.state, 'wait', id=j['id']) for j in (first, second)]
        self.assertEqual([a['exit_code'], b['exit_code']], [0, 0])
        self.assertLessEqual(a['finished'], b['started'])

    def test_client_disconnect_keeps_detached_job_and_stale_token_is_rejected(self):
        job = self.submit('print("detached")')
        self.assertEqual(jobs.rpc(self.state, 'wait', id=job['id'])['exit_code'], 0)
        with self.assertRaisesRegex(RuntimeError, 'live scheduler lease'):
            jobs.rpc(self.state, 'lease', id=job['id'], token='old', pid=os.getpid())


class AdmissionTests(unittest.TestCase):
    def test_unmanaged_work_resets_the_entire_quiet_interval(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = jobs.Queue(Path(temp))
            job = {'cancelled': False, 'quiet': 2, 'status': 'waiting_external'}
            queue.jobs['1'] = job
            with patch.object(jobs, 'external_jobs', side_effect=[[], ['compiler'], [], [], []]) as probe, \
                    patch.object(jobs.time, 'monotonic', side_effect=[0, 1, 2, 3, 4]), \
                    patch.object(queue.condition, 'wait'):
                self.assertTrue(queue.admit(job))
            self.assertEqual(probe.call_count, 5)

    def test_known_external_jobs_and_cargo_test_executables_are_detected(self):
        raw = '1 0.0 /a path/cargo\n2 20.0 /target/debug/deps/cell_test-hash\n3 50.0 /usr/bin/editor\n'
        with patch.object(jobs.subprocess, 'check_output', return_value=raw):
            self.assertEqual(len(jobs.external_jobs()), 2)

    def test_external_process_and_inspection_failure_keep_job_waiting(self):
        import threading
        with tempfile.TemporaryDirectory() as temp:
            queue = jobs.Queue(Path(temp))
            job = {'cancelled': False, 'quiet': 0, 'status': 'waiting_external'}
            queue.jobs['1'] = job
            result = []
            with patch.object(jobs, 'external_jobs', side_effect=RuntimeError('ps failed')):
                thread = threading.Thread(target=lambda: result.append(queue.admit(job)))
                thread.start()
                eventually(lambda: bool(job.get('blockers')))
                self.assertIn('inspection failed', job['blockers'][0])
                with queue.condition:
                    job['cancelled'] = True
                    queue.condition.notify_all()
                thread.join(2)
            self.assertEqual(result, [False])


if __name__ == '__main__':
    unittest.main()
