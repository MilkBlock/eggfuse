#!/usr/bin/env python3
"""Upper opportunity on saved reuse entries; no claim about all fact births."""
import collections
import json
import sys
from pathlib import Path
from analyze_owner_gaps import entry_sources
from analyze_rhs_owners import analyze as validate


def extra_ports(groups):
    return max((len(set.union(*g)) - max(map(len, g)) for g in groups if g), default=0)


def analyze(catalog, audit):
    validate(audit)
    if catalog['program_sha256'] != audit['program_sha256']: raise ValueError('different program')
    seen = set()
    counts = collections.Counter()
    rules = collections.Counter()
    for b in audit['rhs_projection_trace']['trace']['boundaries']:
        if b['prior_status'] != 'visible' or b['cell'] in seen: continue
        seen.add(b['cell'])
        links = b['owner_links']
        if links is None:
            counts['ownership_unavailable'] += 1
            continue
        groups = collections.defaultdict(list)
        for entry, a in entry_sources(links, catalog['entries'][b['rule']]).items():
            loc, fact = a['location'], a['receipt'].get('Fact')
            if loc is None or fact is None: continue
            shape = catalog['shapes'][loc['shape']]
            fields = catalog['program_fields'][shape['programs'][loc['ordinal']]][fact['op']]
            symbols = {s['symbol'] for s in catalog['sources'][b['rule']]
                       if s['entry'] == entry and s['column'] < len(fields) and fields[s['column']] is not None}
            groups[loc['component']].append(symbols)
        extra = extra_ports(groups.values())
        counts['distinct_cells_observed'] += 1
        counts['cells_with_extra_ports'] += extra > 0
        counts['extra_ports_over_best_single_anchor'] += extra
        if extra: rules[b['rule']] += 1
    return dict(scope='offline typed-symbol opportunity on first visible-reuse boundary per Cell; not executed savings',
        program_sha256=audit['program_sha256'], counts=dict(counts),
        eligible_cells_by_rule=dict(rules), limitations=[
            'Only already retained witnesses in the existing reuse trace are available.',
            'This is not a census of all creation-time ownership Entries.',
            'Compare to best single anchor, not necessarily the source actually chosen.',
            'Count distinct child symbols, never repeated parent columns or multiple observations of one Cell.',
            'Missing scalar positions and sources in different components are not merged.',
            'Potential port sharing does not establish a removable source frame or fact.',
            'No additional runtime guards, indexes or representation are admitted by this analysis.'
        ])


if __name__ == '__main__':
    result = analyze(json.loads(Path(sys.argv[1]).read_text()), json.loads(Path(sys.argv[2]).read_text()))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['counts']))
