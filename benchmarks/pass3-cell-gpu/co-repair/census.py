"""Price same-union fanout against the live physical owners, before each union links."""
import argparse
from collections import Counter
import json
from pathlib import Path

from collect import read, digest


def census(folder, schemas):
    cpu = read(folder/'cpu-check.json')
    log = folder/'observation/events.json'
    if digest(log) != cpu['events_sha256']:
        raise ValueError('event log differs from the aligned runtime output')
    events = read(log)
    counters = Counter()
    histogram = Counter()
    workloads = Counter()
    for run, batch in enumerate(events,1):
        for i, e in enumerate(batch):
            if e[0] != 'displaced':
                continue
            _, losing, survivor, records = e
            assert batch[i+1] == ['union',losing,survivor]
            owners = set()
            witnesses = set()
            functions = unsupported = False
            readers = set()
            writers = set()
            for dependency, table, fields in records:
                field = dependency.get('Fact')
                if field is None:
                    identity = ('function',dependency['Function'])
                    owner = identity
                    functions = True
                else:
                    identity = ('fact',field['cell'],field['op'])
                    owner = ('cell',field['cell'])
                assert identity not in witnesses
                witnesses.add(identity)
                owners.add(owner)
                if fields is None or not fields:
                    unsupported = True
                if field is not None and table is not None and fields:
                    table_shape = schemas[table]
                    if table_shape['kind'] != 'constructor':continue
                    last = len(table_shape['schema'])-1
                    if last in fields:
                        writers.add(owner)
                    if any(pos<last for pos in fields):
                        readers.add(owner)
            n=len(owners)
            histogram[n]+=1
            counters['effective_unions']+=1
            counters['subscriber_rows']+=len(witnesses)
            counters['distinct_owners_summed']+=n
            counters['no_subscribers']+=int(not n)
            counters['involves_function']+=int(functions)
            counters['has_unresolved_column']+=int(unsupported)
            counters['single_physical_owner']+=int(n==1 and not functions and not unsupported)
            # A necessary size bound only. Only count cross-owner result->key
            # incidences, retaining every unrelated function/other subscriber.
            linked=bool(writers and readers and len(writers|readers)>1)
            counters['has_cross_owner_result_key']+=int(linked)
            if linked:
                counters['cross_owner_subscribers']+=len(witnesses)
                counters['with_external_functions']+=int(functions)
                if not functions and not unsupported:
                    for cap in (2,3):
                        counters[f'all_registered_fit_{cap}_owners']+=int(n<=cap)
            workloads[run]+=len(witnesses)
    assert counters['effective_unions']==cpu['unions'] and counters['subscriber_rows']==cpu['subscribers']
    return dict(counts=dict(counters),owner_histogram=dict(sorted(histogram.items())),
                source_runs_with_registered_work=sum(v>0 for v in workloads.values()))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('corpus','reference','output'):p.add_argument(n,type=Path)
    args=p.parse_args();results={}
    for name,item in read(args.corpus/'collection.json').items():
        if 'error' in item:raise ValueError((name,item))
        path=args.reference/name if item['split']=='anchor' else args.corpus/name
        schemas=read(path/'program.json')['recipe']['tables']
        results[name]=census(args.corpus/name,schemas)
    args.output.write_text(json.dumps(results,indent=2)+'\n')
