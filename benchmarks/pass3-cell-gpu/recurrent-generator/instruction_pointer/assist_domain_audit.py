"""Compare native search takeover on the identical frozen Actor stream and every visible input."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryFile

from alternate_proofs import digest


def audit(folder, binary, packets, audit_mode):
    capture = folder/'capture.json'
    reference = json.loads(capture.read_bytes() if capture.is_file() else subprocess.check_output(
        [binary,'reference',folder/'program.json','-','audit']))
    grouped = defaultdict(list)
    for packet in packets:
        grouped[packet['run']].append(packet)
    context = hashlib.sha256()
    frames = 0
    cmd = [binary, 'assist', folder/'program.json', '-', audit_mode]
    with TemporaryFile() as errors, subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors) as proc:
        try:
            for line in proc.stdout:
                frame = json.loads(line)
                if 'role' in frame:
                    report = frame
                    break
                frames += 1
                if frame['run'] != frames:
                    raise ValueError('out-of-order native context')
                context.update(line)
                proc.stdin.write(json.dumps(grouped.pop(frames, [])).encode()+b'\n')
                proc.stdin.flush()
            else:
                errors.seek(0)
                raise ValueError('receiver terminated: '+errors.read().decode())
        finally:
            proc.stdin.close()
        if proc.wait() or grouped or frames != reference['runs']:
            raise ValueError('incomplete replay')
    keys = ['schedule','state_sha']
    if audit_mode == 'audit':
        keys += ['rhs','writes','events','resumes']
    for k in keys:
        if reference[k] != report[k]:
            raise ValueError(f'{folder.name}: changed {k}')
    counts = report['counts']
    if (report['unused'] or len(packets) != counts['accepted']+counts['duplicates']+sum(counts['rejected'].values())
            or counts['accepted']+report['assist']['residual_commits'] != reference['matches']):
        raise ValueError('receipt ledger differs')
    return dict(frames=frames,context=context.hexdigest(),state_sha=report['state_sha'],issued=len(packets),
                residual_candidates=report.get('residual_candidates'),
                counts=counts,commits=reference['matches'],assist=report['assist'],native_seconds=report['seconds'],
                verify_seconds=report['verify_seconds'],repair_seconds=report['repair_phase_seconds'])


def compare(folder, path, binaries):
    packets = json.loads(path.read_bytes())
    arms = {arm:audit(folder,binary,packets,'audit') for arm,binary in binaries.items()}
    base=arms['baseline']
    for arm,row in arms.items():
        if any(row[k]!=base[k] for k in ('frames','context','counts','state_sha','commits')):
            raise ValueError('changed neural ingress or signed outcome in '+arm)
    return dict(mode='assist with recorded neural requests',program=digest(folder/'program.json'),
                receiver={k:digest(v) for k,v in binaries.items()},issues=digest(path),arms=arms)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('folder','issues','baseline','treatment','out'): p.add_argument(name,type=Path)
    a=p.parse_args()
    a.out.write_text(json.dumps(compare(a.folder,a.issues,dict(baseline=a.baseline,treatment=a.treatment)),indent=2)+'\n')
