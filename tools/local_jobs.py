#!/usr/bin/env python3
"""One local FIFO for CPU experiments across worktrees; Python standard library only."""
import argparse
import collections
import fcntl
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time

PROTOCOL = 1
TERMINAL = {'done', 'cancelled', 'interrupted', 'failed_start'}
DEFAULT_STATE = Path.home() / '.local/state/eggfuse-jobs'


def classify(executable):
    p = Path(executable)
    if p.name in ('cargo', 'rustc'):
        return 'compiler'
    if (p.name in ('batch_cell_learning', 'runtime_storage_peak', 'eggfuse-cell-runtime',
                  'eggfuse-cell-compiler', 'candidate-runtime', 'control-runtime', 'baseline-runtime')
            or 'target/debug/examples/' in executable or 'target/release/examples/' in executable
            or (p.parent.name == 'deps' and p.parent.parent.name in ('debug', 'release'))
            or (p.parent.name == 'binaries' and p.name.isdigit())):
        return 'workload'
    return None


def external_jobs():
    raw = subprocess.check_output(['ps', '-axww', '-o', 'pid=,pcpu=,comm='], text=True)
    return [line.strip() for line in raw.splitlines()
            if len(line.split(None, 2)) == 3 and classify(line.split(None, 2)[2])]


def group_members(group, exclude=()):
    raw = subprocess.check_output(['ps', '-ax', '-o', 'pid=,pgid=,stat='], text=True,
                                  start_new_session=True)
    return [int(pid) for pid, pgid, state in (line.split() for line in raw.splitlines())
            if int(pgid) == group and int(pid) not in exclude and not state.startswith('Z')]


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def public(job):
    return {k: v for k, v in job.items() if k not in ('env', 'token', 'process', 'gate')}


class Queue:
    def __init__(self, directory, guard='known'):
        self.directory = directory
        self.guard = guard
        self.condition = threading.Condition(threading.RLock())
        self.pending = collections.deque()
        self.stopping = False
        self.active = None
        self.jobs = {}
        self.recovering = set()
        self.journal = directory / 'jobs.json'
        if self.journal.exists():
            self.jobs = json.loads(self.journal.read_text())['jobs']
            for job in self.jobs.values():
                if job['status'] not in TERMINAL:
                    if job.get('pid'):
                        self.recovering.add(job['pid'])
                    job.update(status='interrupted', finished=time.time(),
                               error='Scheduler restarted; command was not automatically replayed.')
        self.next_id = max(map(int, self.jobs), default=0) + 1
        self.save()

    def save(self):
        atomic_json(self.journal, {'protocol': PROTOCOL, 'guard': self.guard,
                                  'jobs': {k: public(v) for k, v in self.jobs.items()}})

    def submit(self, request):
        argv, cwd = request['argv'], request['cwd']
        if not argv or not all(isinstance(a, str) for a in argv) or not Path(cwd).is_dir():
            raise ValueError('Expected an argv array and an existing working directory')
        if request['kind'] not in ('compute', 'timing'):
            raise ValueError('Unknown job kind')
        quiet = float(request.get('quiet', 3 if request['kind'] == 'timing' else 0))
        if not 0 <= quiet <= 3600:
            raise ValueError('quiet must be between 0 and 3600 seconds')
        with self.condition:
            if self.stopping:
                raise ValueError('Scheduler is stopping')
            identity = str(self.next_id)
            self.next_id += 1
            job = dict(id=identity, kind=request['kind'], argv=argv, cwd=cwd,
                       env=request['env'], token=secrets.token_hex(24), quiet=quiet,
                       status='queued', submitted=time.time(), cancelled=False,
                       log=str(self.directory / f'job-{identity}.log'), guard=self.guard)
            self.jobs[identity] = job
            self.pending.append(identity)
            self.save()
            self.condition.notify_all()
            return public(job)

    def cancel(self, identity):
        with self.condition:
            job = self.jobs[identity]
            if job['status'] in TERMINAL:
                return public(job)
            job['cancelled'] = True
            if job['status'] in ('queued', 'waiting_external'):
                job.update(status='cancelled', exit_code=130, finished=time.time())
            elif job.get('pid'):
                self.signal_group(job, signal.SIGTERM)
                threading.Thread(target=self.escalate, args=(identity,), daemon=True).start()
            self.save()
            self.condition.notify_all()
            return public(job)

    def signal_group(self, job, signum):
        if job['status'] in ('running', 'draining'):
            try:
                os.killpg(job['pid'], signum)
            except ProcessLookupError:
                pass

    def escalate(self, identity):
        with self.condition:
            self.condition.wait_for(lambda: self.jobs[identity]['status'] in TERMINAL, timeout=5)
            self.signal_group(self.jobs[identity], signal.SIGKILL)

    def wait(self, identity):
        with self.condition:
            self.condition.wait_for(lambda: self.jobs[identity]['status'] in TERMINAL)
            return public(self.jobs[identity])

    def lease(self, request):
        with self.condition:
            job = self.jobs.get(request.get('id'))
            if (job is None or job['status'] != 'running'
                    or job.get('token') != request.get('token')
                    or os.getpgid(request['pid']) != job.get('pid')):
                raise ValueError('No live scheduler lease for this process group')
            return public(job)

    def run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending or self.stopping)
                if self.stopping:
                    return
                identity = self.pending.popleft()
                job = self.jobs[identity]
                if job['status'] in TERMINAL:
                    continue
                self.active = identity
                job['status'] = 'waiting_external'
                self.save()
            try:
                if self.admit(job):
                    self.execute(job)
            except Exception as error:
                with self.condition:
                    job.update(status='failed_start', exit_code=125, error=str(error), finished=time.time())
            finally:
                with self.condition:
                    self.active = None
                    job.pop('env', None)
                    job.pop('token', None)
                    self.save()
                    self.condition.notify_all()

    def admit(self, job):
        quiet_since = None
        while True:
            with self.condition:
                if job['cancelled']:
                    return False
            try:
                blockers = external_jobs() if self.guard == 'known' else []
                for group in tuple(self.recovering):
                    if group_members(group):
                        blockers.append(f'Waiting for interrupted managed process group {group}')
                    else:
                        self.recovering.remove(group)
            except Exception as error:
                blockers = [f'Process inspection failed: {error}']
            now = time.monotonic()
            quiet_since = None if blockers else (now if quiet_since is None else quiet_since)
            with self.condition:
                if blockers != job.get('blockers'):
                    job['blockers'] = blockers
                    self.save()
                if quiet_since is not None and now - quiet_since >= job['quiet']:
                    return not job['cancelled']
                self.condition.wait(timeout=1)

    def execute(self, job):
        # The guardian cannot start the command until its identity is saved.
        # A daemon crash closes this pipe and kills the guardian's own group.
        read_gate, write_gate = os.pipe()
        process = None
        try:
            env = dict(job['env'], EGGFUSE_JOB_STATE=str(self.directory),
                       EGGFUSE_JOB_ID=job['id'], EGGFUSE_JOB_TOKEN=job['token'])
            with open(job['log'], 'wb') as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                    'child', str(read_gate), *job['argv']], cwd=job['cwd'], env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True, pass_fds=(read_gate,))
            os.close(read_gate)
            read_gate = None
            with self.condition:
                job.update(status='running', pid=process.pid, started=time.time())
                self.save()
                if job['cancelled']:
                    self.signal_group(job, signal.SIGTERM)
                else:
                    os.write(write_gate, b'G')
            code = process.wait()
            with self.condition:
                job['status'] = 'draining'
            # Includes descendants after an abruptly killed guardian. Never
            # release the queue while the owned group still has live children.
            while group_members(process.pid):
                with self.condition:
                    self.condition.wait(timeout=0.2)
            with self.condition:
                job.update(status='cancelled' if job['cancelled'] else 'done',
                           exit_code=130 if job['cancelled'] else (128 - code if code < 0 else code),
                           finished=time.time())
        finally:
            if read_gate is not None:
                os.close(read_gate)
            os.close(write_gate)
            if process is not None:
                process.wait()
                while group_members(process.pid):
                    time.sleep(0.2)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline(4 * 1024 * 1024)
            request = json.loads(raw)
            queue = self.server.queue
            action = request['action']
            if action == 'ping':
                result = dict(protocol=PROTOCOL, pid=os.getpid(), guard=queue.guard)
            elif action == 'submit':
                result = queue.submit(request)
            elif action == 'wait':
                result = queue.wait(request['id'])
            elif action == 'cancel':
                result = queue.cancel(request['id'])
            elif action == 'lease':
                result = queue.lease(request)
            elif action == 'status':
                with queue.condition:
                    result = dict(active=queue.active, guard=queue.guard,
                                  jobs=[public(j) for j in queue.jobs.values()])
            elif action == 'stop':
                with queue.condition:
                    if any(j['status'] not in TERMINAL for j in queue.jobs.values()):
                        raise ValueError('Stop requires an idle queue; cancel jobs explicitly first')
                    queue.stopping = True
                    queue.condition.notify_all()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                result = {'stopped': True}
            else:
                raise ValueError('Unknown action')
            response = {'ok': True, 'result': result}
        except Exception as error:
            response = {'ok': False, 'error': str(error)}
        try:
            self.wfile.write(json.dumps(response).encode() + b'\n')
        except (BrokenPipeError, ConnectionResetError):
            pass  # Detached jobs survive a disconnected observer.


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def serve(directory, guard):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    with (directory / 'daemon.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        address = directory / 'queue.sock'
        address.unlink(missing_ok=True)
        with Server(str(address), Handler) as server:
            server.queue = Queue(directory, guard)
            threading.Thread(target=server.queue.run, daemon=True).start()
            try:
                server.serve_forever(poll_interval=1)
            finally:
                address.unlink(missing_ok=True)
    return 0


def rpc(directory, action, **values):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(directory / 'queue.sock'))
        connection.sendall(json.dumps(dict(action=action, **values)).encode() + b'\n')
        with connection.makefile('rb') as stream:
            raw = stream.readline()
    if not raw:
        raise RuntimeError('Scheduler disconnected; inspect status before resubmitting')
    response = json.loads(raw)
    if not response['ok']:
        raise RuntimeError(response['error'])
    return response['result']


def ensure_daemon(directory):
    try:
        return rpc(directory, 'ping')
    except (FileNotFoundError, ConnectionRefusedError):
        pass
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'daemon.log').open('ab') as log:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--state-dir', str(directory),
                          'serve'], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True)
    for _ in range(100):
        try:
            return rpc(directory, 'ping')
        except (FileNotFoundError, ConnectionRefusedError):
            time.sleep(0.05)
    raise RuntimeError(f'Scheduler did not start; inspect {directory / "daemon.log"}')


def current_lease():
    if not os.environ.get('EGGFUSE_JOB_ID'):
        return None
    directory = Path(os.environ['EGGFUSE_JOB_STATE'])
    return rpc(directory, 'lease', id=os.environ['EGGFUSE_JOB_ID'],
               token=os.environ.get('EGGFUSE_JOB_TOKEN'), pid=os.getpid())


def wait_job(directory, identity, print_log=True):
    def interrupt(signum, frame):
        rpc(directory, 'cancel', id=identity)
    previous = {s: signal.signal(s, interrupt) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        job = rpc(directory, 'wait', id=identity)
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)
    if print_log and Path(job['log']).exists():
        with open(job['log'], 'rb') as log:
            shutil.copyfileobj(log, sys.stdout.buffer)
    if job.get('error'):
        print(job['error'], file=sys.stderr)
    return job.get('exit_code', 125)


def run_command(directory, argv, kind='compute', quiet=None, detached=False):
    lease = current_lease()
    if lease:
        if detached:
            raise RuntimeError('Detached nested jobs would outlive their lease; submit outside the job')
        if kind == 'timing' and lease['kind'] != 'timing':
            raise RuntimeError('Wrap the whole pipeline with --kind timing before starting measurements')
        # Same process group and original argv; no second queue acquisition.
        os.execvpe(argv[0], argv, os.environ)
    ensure_daemon(directory)
    request = dict(argv=argv, cwd=str(Path.cwd()), env=dict(os.environ), kind=kind)
    if quiet is not None:
        request['quiet'] = quiet
    job = rpc(directory, 'submit', **request)
    print(f'job {job["id"]}: queued {kind}; log {job["log"]}', file=sys.stderr, flush=True)
    if detached:
        print(job['id'])
        return 0
    return wait_job(directory, job['id'])


def child(gate, argv):
    os.set_inheritable(gate, False)
    if os.read(gate, 1) != b'G':
        return 125
    def watch_parent():
        # No timer or polling during the measured command.
        if not os.read(gate, 1):
            os.killpg(os.getpgrp(), signal.SIGKILL)
    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        code = subprocess.call(argv)
    except OSError as error:
        print(f'Cannot start {argv[0]}: {error}', file=sys.stderr)
        return 127 if isinstance(error, FileNotFoundError) else 126
    while group_members(os.getpgrp(), exclude=(os.getpid(),)):
        time.sleep(0.2)
    return 128 - code if code < 0 else code


def install():
    package = Path.home() / '.local/share/eggfuse-jobs'
    launcher = Path.home() / '.local/bin/eggfuse-job'
    if launcher.exists() and 'eggfuse-jobs/local_jobs.py' not in launcher.read_text():
        raise RuntimeError(f'Refusing to replace unrelated launcher {launcher}')
    package.mkdir(parents=True, exist_ok=True)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    source = package / 'local_jobs.py'
    if Path(__file__).resolve() != source.resolve():
        if source.exists() and source.read_bytes() != Path(__file__).read_bytes():
            try:
                rpc(DEFAULT_STATE, 'ping')
            except (FileNotFoundError, ConnectionRefusedError):
                pass
            else:
                raise RuntimeError('Stop the idle scheduler before updating its installed code')
        shutil.copy2(Path(__file__), source)
    launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' '
                        + shlex.quote(str(source)) + ' "$@"\n')
    launcher.chmod(0o755)
    print(launcher)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path,
                        default=Path(os.environ.get('EGGFUSE_JOB_STATE', DEFAULT_STATE)))
    commands = parser.add_subparsers(dest='action', required=True)
    for action in ('run', 'submit'):
        p = commands.add_parser(action)
        p.add_argument('--kind', choices=('compute', 'timing'), default='compute')
        p.add_argument('--quiet', type=float)
        p.add_argument('command', nargs=argparse.REMAINDER)
    for action in ('wait', 'cancel'):
        commands.add_parser(action).add_argument('id')
    commands.add_parser('status')
    commands.add_parser('stop')
    commands.add_parser('install')
    p = commands.add_parser('serve')
    p.add_argument('--guard', choices=('known', 'none'), default='known',
                   help='none is for isolated scheduler tests; never timing acceptance')
    p = commands.add_parser('child')
    p.add_argument('gate', type=int)
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    directory = args.state_dir.expanduser().resolve()
    if args.action == 'serve':
        return serve(directory, args.guard)
    if args.action == 'child':
        return child(args.gate, args.command)
    if args.action == 'install':
        return install()
    if args.action in ('run', 'submit'):
        argv = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not argv:
            parser.error('supply a command after --')
        return run_command(directory, argv, args.kind, args.quiet, args.action == 'submit')
    ensure_daemon(directory)
    if args.action == 'wait':
        return wait_job(directory, args.id)
    result = rpc(directory, args.action, **({'id': args.id} if args.action == 'cancel' else {}))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f'eggfuse-job: {error}', file=sys.stderr)
        raise SystemExit(125)
