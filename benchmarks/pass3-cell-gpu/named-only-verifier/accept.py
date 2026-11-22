"""Replay issued proofs first. Only then start the isolated reference process."""
import argparse
import json
from pathlib import Path
import subprocess


def execute(command, request):
    proc = subprocess.run(command, input=json.dumps(request)+'\n', text=True,
                          check=True, capture_output=True)
    return json.loads(proc.stdout)


def evaluate(verifier, reference, program, plans, packets):
    observed = execute([verifier, program], packets)
    if observed['protocol'] != 'named-only/v1':
        raise ValueError('expected the named-only receiver')
    if observed['accepted'] + observed['rejected'] + observed['unused'] != len(packets):
        raise ValueError('issued packet ledger mismatch')
    source = execute([reference, program, plans], {'baseline': True, 'audit': True})
    checks = {key: observed[key] == source[key] for key in
              ('rhs', 'writes', 'resumes', 'events', 'state_sha')}
    checks['schedule'] = observed['schedule'] == source['schedule']
    return dict(status='pass' if all(checks.values()) else 'difference', checks=checks,
                **{key:observed[key] for key in ('accepted','rejected','unused','named_reads','run_matches')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('verifier','reference','program','plans','issued'):
        parser.add_argument(name,type=Path)
    a = parser.parse_args()
    result = evaluate(a.verifier,a.reference,a.program,a.plans,json.loads(a.issued.read_bytes()))
    print(json.dumps(result,indent=2))
    raise SystemExit(result['status'] != 'pass')
