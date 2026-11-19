"""Invoke the Cell compiler and read the static routes used by CrossRun."""
import json
from pathlib import Path
import subprocess
import tempfile

from ._recipe import INPUT_ARITIES, lower

SCHEMA = 'eggfuse.crossrun.direct-input-projection/v1'
STAGES = (('make', ('A', 'B'), 'Pair'), ('finish', ('Pair', 'Request'), 'Result'))


def projection_recipe(path_or_dict):
    """Convert a plan JSON file or decoded plan into immutable tensor-column routes."""
    plan = (path_or_dict if isinstance(path_or_dict, dict)
            else json.loads(Path(path_or_dict).read_text()))
    if plan.get('schema') != SCHEMA:
        raise ValueError(f'expected {SCHEMA}')
    maps = []
    for stage, tables, expected_output in STAGES:
        rule = plan['rules'][stage]
        if (len(rule['inputs']) != 2 or set(rule['inputs']) != set(tables)
                or rule['output_table'] != expected_output or len(rule['outputs']) != 5):
            raise ValueError(f'unsupported {stage} table interface')
        routes = []
        for side, column in rule['outputs']:
            if type(side) is not int or side not in (0, 1):
                raise ValueError(f'invalid input side {side!r} in {stage}')
            table = rule['inputs'][side]
            if type(column) is not int or not 0 <= column < INPUT_ARITIES[table]:
                raise ValueError(f'invalid column {column!r} for {table}')
            routes.append((tables.index(table), column))
        maps.append(tuple(routes))
    return tuple(maps)


def compile_projection(source, *, compiler_binary, output_path=None):
    """Compile scheduled .egg text (or a Path) using the Rust real_completion_dataset executable.

    This driver consumes the typed recipe returned by the Rust program. The source
    must define the supported make/finish interfaces and their Run schedule.
    """
    executable = Path(compiler_binary).expanduser().resolve(strict=True)
    text = source.read_text() if isinstance(source, Path) else source
    if not isinstance(text, str):
        raise TypeError('source must be .egg text or a pathlib.Path')
    with tempfile.TemporaryDirectory(prefix='eggfuse-compile-') as temporary:
        work = Path(temporary)
        request = work / 'request.json'
        artifact = work / 'artifact.json'
        request.write_text(json.dumps({'cases': [dict(id='eggfuse-python', source=text, include_program=True)]}))
        subprocess.run([str(executable), str(request), str(artifact)], check=True)
        result = json.loads(artifact.read_text())['cases'][0]
        if [step['ruleset'] for step in result['steps']] != ['make', 'finish']:
            raise ValueError('expected a make Run followed by a finish Run')
        plan = {'schema': SCHEMA, 'rules': lower(result['compiled_program']['recipe'])}
    projection_recipe(plan)
    if output_path is not None:
        target = Path(output_path)
        with tempfile.NamedTemporaryFile('w', dir=target.parent, delete=False) as stream:
            scratch = Path(stream.name)
            try:
                json.dump(plan, stream, indent=2, sort_keys=True)
                stream.write('\n')
            except BaseException:
                scratch.unlink(missing_ok=True)
                raise
        try:
            scratch.replace(target)
        finally:
            scratch.unlink(missing_ok=True)
    return plan
