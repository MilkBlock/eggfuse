#!/usr/bin/env python3
"""Inspect frozen arm64 binaries; static code sizes are not dynamic work counts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess


METHODS = {
    'publication': '::Publication::publish::h',
    'completion': '::publish_finished_tables::h',
    'run': '::Executor::run::h',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect(reference, output, objdump):
    binary = reference / 'candidate-runtime'
    expected = json.loads((reference / 'manifest.json').read_text())['runtime_sha256']
    assert digest(binary) == expected, 'frozen binary changed'
    symbols = subprocess.check_output([objdump, '--syms', '--demangle', str(binary)], text=True)
    assert 'file format mach-o arm64' in symbols
    names = {}
    for key, method in METHODS.items():
        found = [s.split()[-1] for s in symbols.splitlines()
                 if method in s and '__TEXT,__text' in s and 'core::ptr' not in s]
        assert len(found) == 1, (key, found)
        names[key] = found[0]
    command = [objdump, '--disassemble', '--demangle', '--no-show-raw-insn',
               '--disassemble-symbols=' + ','.join(names.values()), str(binary)]
    assembly = subprocess.check_output(command, text=True)
    output.mkdir()
    (output / 'symbols.txt').write_text(symbols)
    (output / 'hot.asm').write_text(assembly)
    blocks = re.split(r'(?m)^(?=[0-9a-f]+ <)', assembly)[1:]
    functions = {}
    for key, name in names.items():
        block, = [b for b in blocks if b.splitlines()[0].endswith('<' + name + '>:')]
        instructions = [line.split(':', 1)[1].strip() for line in block.splitlines()[1:]
                        if re.match(r'^[0-9a-f]+:', line)]
        # These methods save registers and allocate their frame before the
        # first 20 instructions. Keep the raw prologue alongside the number.
        prologue = instructions[:20]
        frame = 0
        for instruction in prologue:
            m = re.match(r'sub\s+sp, sp, #(0x[0-9a-f]+)(?:, lsl #(\d+))?', instruction)
            if m:
                frame += int(m[1], 16) << int(m[2] or 0)
            m = re.search(r'\[sp, #-(0x[0-9a-f]+)\]!', instruction)
            if m:
                frame += int(m[1], 16)
        functions[key] = dict(symbol=name, instruction_count=len(instructions),
                              initial_stack_bytes=frame, prologue=prologue)
    return dict(runtime_sha256=expected, command=command, functions=functions,
                assembly_sha256=digest(output / 'hot.asm'))


def main(control, candidate, output):
    jobs = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'tools/local_jobs.py'))
    assert jobs['current_lease']() is not None, 'run through eggfuse-job'
    objdump = subprocess.check_output(['xcrun', '--find', 'llvm-objdump'], text=True).strip()
    output.mkdir(parents=True)
    report = {'scope': 'static frozen arm64 code; not a performance or dynamic instruction measurement',
              'lanes': {label: inspect(root, output / label, objdump)
                        for label, root in (('control', control), ('candidate', candidate))}}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    for label, lane in report['lanes'].items():
        print(label, {k: {f: v[f] for f in ('instruction_count', 'initial_stack_bytes')}
                      for k, v in lane['functions'].items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('control', 'candidate', 'output'):
        parser.add_argument(name, type=Path)
    main(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})
