"""Alternate native reference and teacher replay in separate processes with end-to-end clocks."""
import argparse
import json
import subprocess
from pathlib import Path
from time import perf_counter

from alternate_proofs import digest


def controls(folder, binary, repetitions, mode):
    expected = json.loads((folder / 'capture.json').read_bytes())
    tape = folder / 'tape.json'
    samples = []
    for repetition in range(repetitions + 1):
        roles = ('reference', 'replay')
        for role in (roles[::-1] if repetition % 2 else roles):
            started = perf_counter()
            data = subprocess.check_output([binary, role, folder / 'program.json', tape, mode])
            wall = perf_counter() - started
            report = json.loads(data)
            keys = ('rhs', 'writes', 'resumes', 'events') if mode == 'audit' else ()
            for key in ('schedule','state_sha',*keys):
                if report[key] != expected[key]:
                    raise ValueError(f'{role} differs from capture on {key}')
            if role == 'replay' and (report['unused'] or report['counts']['accepted'] != expected['matches']):
                raise ValueError('teacher replay did not consume the exact ledger')
            if repetition:
                samples.append(dict(role=role, round=repetition, wall_seconds=wall,
                                    source_search=report['source_search_phase_seconds'],
                                    verify=report.get('verify_seconds', 0),
                                    residual_visits=report['residual_candidates']))
    return dict(samples=samples, mode=mode, program=digest(folder/'program.json'), binary=digest(binary), state_sha=expected['state_sha'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('folder','binary','output'):
        parser.add_argument(name,type=Path)
    parser.add_argument('--repetitions', type=int, default=4)
    parser.add_argument('--mode',choices=('audit','time'),default='audit')
    args=parser.parse_args()
    args.output.write_text(json.dumps(controls(args.folder,args.binary,args.repetitions,args.mode),indent=2)+'\n')
