"""Build an offline compiler request from a shared ruleset and input facts."""
import argparse
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def make_case(fixture, rules):
    facts = []
    for table in ('A', 'B', 'Request'):
        for row in fixture[table]:
            if len(row) != 3 or any(type(value) is not int for value in row):
                raise ValueError(f'invalid i64 row in {table}')
            facts.append(f"({table} {' '.join(map(str, row))})")
    schedule = '(run-schedule (seq (run make) (run finish)))'
    return {'id': fixture['id'], 'source': '\n'.join([rules, *facts, schedule, '']),
            'include_program': True, 'include_bindings': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--fixtures', type=Path, default=HERE/'fixtures.json')
    args = parser.parse_args()
    fixtures = json.loads(args.fixtures.read_text())
    rules = (HERE/'rules.egg').read_text()
    args.output.write_text(json.dumps({'cases': [make_case(x, rules) for x in fixtures]}, indent=2) + '\n')


if __name__ == '__main__':
    main()
