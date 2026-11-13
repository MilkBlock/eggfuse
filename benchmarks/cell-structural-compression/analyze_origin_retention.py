#!/usr/bin/env python3
"""Join typed whole-program readers with retained runtime function origins.

This is an opportunity census, not a license to delete rows or skip effects.
"""
import collections
import json
import sys
from pathlib import Path


def table_calls(value):
    if isinstance(value, dict):
        call = value.get('call', {})
        if isinstance(call, dict) and 'table' in call:
            yield call['table']
        for child in value.values():
            yield from table_calls(child)
    elif isinstance(value, list):
        for child in value:
            yield from table_calls(child)


def readers(program):
    found = collections.defaultdict(list)
    for rid, rule in enumerate(program['recipe']['rules']):
        for table in table_calls(rule['query']):
            found[table].append(['query', rid])
        for op, effect in enumerate(rule['effects']):
            if effect['op'] == 'let':
                for table in table_calls(effect):
                    found[table].append(['rhs_read', rid, op])
    # A merge read is live even when no query atom mentions its table.
    for merge in program['merge_programs']['programs']:
        for table in table_calls(merge['operations']):
            found[table].append(['merge_read', merge['table']])
    for table in table_calls(program['recipe']['control']):
        found[table].append(['control_read'])
    return found


def analyze(program, heap, baseline):
    assert heap['program_sha256'] == program['sha256'] == baseline['program_sha256']
    assert heap['final_state_sha256'] == baseline['final_state_sha256']
    assert heap['runs'] == baseline['runs']
    uses = readers(program)
    census = {r['table']: r for r in heap['source_storage']['origin_tables']}
    tables = []
    for table in program['recipe']['tables']:
        name = table['name']
        if (table['kind'] != 'function' or table['schema'][-1]['kind'] != 'Unit'
                or table['merge_expr'] != {'var': 'old'} or uses[name]):
            continue
        observed = census.get(name, dict(live_function_rows=0, retained_origins=0,
                                        inline_writers=0, source_cells=[]))
        tables.append(dict(table=name, **{k:v for k,v in observed.items() if k != 'table'}))
    candidate_sources = set().union(*(set(t['source_cells']) for t in tables))
    other_sources = set().union(*(set(t['source_cells']) for n,t in census.items()
                                 if n not in {t['table'] for t in tables}))
    handoffs = []
    for name in program['marker_tables']:
        observed = census.get(name)
        if not observed or not observed['live_function_rows']:
            continue
        writers = []
        for rid, rule in enumerate(program['recipe']['rules']):
            if any(e['op'] == 'set' and e.get('call', {}).get('table') == name
                   for e in rule['effects']):
                writers.append([rid, rule['metadata']['source_set']])
        query_readers = [[u[1], program['recipe']['rules'][u[1]]['metadata']['source_set']]
                         for u in uses[name] if u[0] == 'query']
        handoffs.append(dict(table=name, live_function_rows=observed['live_function_rows'],
                             retained_origins=observed['retained_origins'],
                             writers=writers, query_readers=query_readers,
                             other_reads=[u for u in uses[name] if u[0] != 'query']))
    handoffs.sort(key=lambda x: (-x['live_function_rows'], x['table']))
    return dict(scope='actual standalone Cell runtime final retained origin census; not native egglog',
                program_sha256=program['sha256'], runs=heap['runs'], final_state_equal=True,
                unread_unit_tables=tables, shared_view_handoffs=handoffs,
                totals={k:sum(t[k] for t in tables) for k in
                        ('live_function_rows','retained_origins','inline_writers')},
                candidate_source_cells=len(candidate_sources),
                sources_also_retained_by_other_tables=len(candidate_sources & other_sources),
                graph_owned_bytes=heap['graph_owned_teardown_bytes'],
                obligations=['Keep rows, dedup, update counts and saturate change signals.',
                             'Other tables, child frames and external Graph callers can retain a source.',
                             'Read absence is source-program scoped, not a general Graph API guarantee.',
                             'Counts are not reclaimable byte estimates or a completed takeover.'])


if __name__ == '__main__':
    p, h, b = (json.loads(Path(s).read_text()) for s in sys.argv[1:4])
    result = analyze(p, h, b)
    Path(sys.argv[4]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('unread_unit_tables', 'shared_view_handoffs')}, indent=2))
