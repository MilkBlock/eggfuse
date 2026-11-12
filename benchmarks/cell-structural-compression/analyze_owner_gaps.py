#!/usr/bin/env python3
"""Classify missed owner connections using checked Entry coordinates."""
import collections
import json
import sys
from pathlib import Path
from analyze_rhs_owners import analyze as validate, same


def entry_sources(links, entries):
    # Old archives mislabeled the Entry ordinal as atom. New archives carry both.
    found = {}
    for a in links['anchors']:
        entry = a.get('entry', a['atom'])
        atom = entries[entry]
        if 'entry' in a and a['atom'] != atom: raise ValueError('Entry atom differs from compiler')
        found[entry] = a
    for a in links['query']:
        for entry, atom in enumerate(entries):
            if atom == a['atom'] and entry not in found: found[entry] = a
    return found


def analyze(catalog, audit):
    validate(audit)
    if catalog['program_sha256'] != audit['program_sha256']:
        raise ValueError('catalog and trace differ')
    transitions = {(k['shape'], k['hop']['source_frame'], k['hop']['rule'], k['hop']['entry'], k['hop']['op'])
                   for k, _ in catalog['transitions']}
    completed = {e['cell']: e for e in audit['rhs_projection_trace']['trace']['events']}
    counts = collections.Counter()
    rules = collections.defaultdict(collections.Counter)
    for b in audit['rhs_projection_trace']['trace']['boundaries']:
        if b['prior_status'] != 'visible' or b['previous_run'] == b['run']: continue
        l = b['owner_links']
        if l is None: continue
        donor = l['donor']
        sources = [l['receiver']] + [a['location'] for a in l['anchors'] + l['query']]
        if l['parent']: sources.append(l['parent']['location'])
        if any(same(s, donor) for s in sources): continue
        entries = catalog['entries'][b['rule']]
        found = entry_sources(l, entries)
        known = [(entry, a) for entry, a in found.items() if a['location'] is not None and 'Fact' in a['receipt']]
        available = []
        for entry, a in known:
            loc = a['location']
            key = (loc['shape'], loc['ordinal'], b['rule'], entry, a['receipt']['Fact']['op'])
            available.append((key in transitions, loc['frames'] < catalog['max_frames']))
        if not known: category = 'no_observed_owned_entry'
        elif any(installed and space for installed, space in available): category = 'installed_transition_with_capacity'
        elif any(space for _, space in available): category = 'unbaked_transition_with_capacity'
        else: category = 'all_observed_sources_at_capacity'
        for c in (counts, rules[b['rule']]):
            c['unconnected_boundaries'] += 1
            c[category] += 1
            c['all_eligible_receipts_observed'] += len(found) == len(entries)
            c['all_eligible_entries_owned'] += len(known) == len(entries)
            c['entry_not_active'] += not l['entry_present']
            completion = completed.get(b['cell'])
            if completion is not None and completion['facts'] == 0:
                c['boundaries_in_cells_without_new_facts'] += 1
                c[category + ':cell_without_new_facts'] += 1
            c['donor_frames_' + str(donor['frames'])] += 1
    return dict(scope='offline classification, not executable closure admission or savings',
        program_sha256=audit['program_sha256'], counts=dict(counts),
        rules={str(r): dict(c) for r,c in sorted(rules.items())},
        obligations=[
            'Installed transitions append the new Cell to a source component; they do not merge a foreign donor.',
            'Capacity is observed on source components, not inferred from donor size.',
            'No observed source is unknown when query witnesses were not retained.',
            'All eligible entries refers to compiler ownership Entries, not all query atoms.',
            'Cell order, actual transition selection, typed key equality, lifecycle and source Run order still require checking.'
        ])


if __name__ == '__main__':
    result = analyze(json.loads(Path(sys.argv[1]).read_text()), json.loads(Path(sys.argv[2]).read_text()))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['counts'], indent=2))
