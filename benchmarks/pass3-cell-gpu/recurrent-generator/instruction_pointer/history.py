"""Read pre-write snapshots and committed provenance. Supervision is separate from port memory."""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import random

from catalog import Catalog


def address(value):
    return value['token'], value['op']


@dataclass(frozen=True)
class Parent:
    node: int
    pc: int
    hashes: tuple


@dataclass(frozen=True)
class Port:
    address: tuple
    kind: str
    root: int
    node: int
    table: int
    version: int
    forwarded: bool
    hashes: tuple
    inputs: tuple


@dataclass
class Snapshot:
    run: int
    epoch: int
    rules: dict
    ports: list
    targets: list


class History:
    """Build a snapshot solely from runtime deltas and receipts, including on free rollouts."""
    def __init__(self, catalog, seed, cache_ports=False):
        self.catalog = catalog
        self.rng = random.Random(seed)
        self.names, self.inverse = {}, {}
        self.templates, self.inputs, self.visible = {}, {}, {}
        self.run = 0
        self.port_cache = {} if cache_ports else None

    def rename(self, a):
        token, pc = a
        if token not in self.names:
            alias = self.rng.getrandbits(62)
            while alias in self.inverse:
                alias = self.rng.getrandbits(62)
            self.names[token] = alias
            self.inverse[alias] = token
        return self.names[token], pc

    def snapshot(self, frame, materialize=True):
        run = frame['run']
        if run != self.run + 1:
            raise ValueError('missing snapshot')
        self.run = run
        catalog = self.catalog
        for req in frame['accepted']:
            if req['run'] != run - 1:
                raise ValueError('receipt crossed an unexpected boundary')
            tpl = ('generated',req['rule'])
            parents = []
            for item in req['parents']:
                src, pc = address(item['address'])
                row = self.visible[src,pc]
                if row['version'] != item['version']:
                    raise ValueError('accepted reference differs from its issue snapshot')
                parents.append(Parent(catalog.outputs[self.templates[src],pc],pc,tuple(row['hashes'])))
            self.templates[req['token']] = tpl
            self.inputs[req['token']] = tuple(zip(catalog.inputs[tpl], parents, strict=True))
        for item in frame['retired']:
            retired = address(item)
            del self.visible[retired]
            if self.port_cache is not None:
                self.port_cache.pop(retired,None)
        for item,row in frame['updates']:
            a = address(item)
            self.visible[a] = row
            if a[0] < 0 and a[0] % 2:
                self.templates[a[0]] = ('initial',row['table'])
        for event in frame['repair_events']:
            if run != event['visible_from_run'] or run != event['run'] + 1:
                raise ValueError('repair leaked across source boundary')
            tpl = ('repair',event['merge_table'])
            parents = []
            for item,value in zip(event['parents'],event['input_hashes'],strict=True):
                src,pc = address(item['address'])
                parents.append(Parent(catalog.outputs[self.templates[src],pc],pc,(value,)))
            self.templates[event['token']] = tpl
            self.inputs[event['token']] = tuple(zip(catalog.inputs[tpl], parents, strict=True))
        if not materialize:
            if self.port_cache is not None:
                self.port_cache.clear()
            return None
        def port(a,row):
            token,pc = a
            tpl = self.templates[token]
            return Port(self.rename(a),tpl[0],catalog.roots[tpl],catalog.outputs[tpl,pc],
                        row['table'],row['version'],row['forwarded'],tuple(row['hashes']),
                        self.inputs.get(token,()))
        if self.port_cache is None:
            ports = [port(a,row) for a,row in self.visible.items()]
        else:
            # Receipts freeze template and parent fields at signing. The native
            # delta carries changes of version, content, forwarding and visibility.
            # Keep the same insertion order and seeded permutation as a full rebuild.
            updates = ((address(item),row) for item,row in frame['updates']) if self.port_cache else self.visible.items()
            for a,row in updates:
                self.port_cache[a] = port(a,row)
            ports = list(self.port_cache.values())
        self.rng.shuffle(ports)
        return Snapshot(run,frame['epoch'],dict(frame['rules']),ports,[])


def stream(directory, seed, runs=None, catalog_type=Catalog, supervision=None):
    raw = (directory/'program.json').read_bytes()
    tape = json.loads((directory/'tape.json').read_bytes())
    if hashlib.sha256(raw).hexdigest() != tape['program_sha256']:
        raise ValueError('compiled program differs from captured history')
    catalog = catalog_type(json.loads(raw))
    history = History(catalog,seed)
    actions = defaultdict(list)
    for req in (tape['requests'] if supervision is None else supervision):
        actions[req['run']].append(req)
    with (directory/'memory.jsonl').open() as records:
        for line in records:
            frame = json.loads(line)
            s = history.snapshot(frame, runs is None or frame['run'] in runs)
            if s is None:
                continue
            for req in actions[s.run]:
                refs = []
                for item in req['parents']:
                    a = address(item['address'])
                    if history.visible[a]['version'] != item['version']:
                        raise ValueError('teacher label does not name the current port version')
                    refs.append(history.rename(a))
                s.targets.append((req['rule'],tuple(refs)))
            yield catalog,s
            if runs is not None and s.run == max(runs):
                break


def load(directory, seed, runs=None):
    pairs = iter(stream(directory,seed,runs))
    catalog,first = next(pairs)
    return catalog,[first,*(snapshot for _,snapshot in pairs)]
