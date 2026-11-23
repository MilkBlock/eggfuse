"""Bake a tensorizable instruction graph from the actual runtime program."""
import hashlib
import json
from functools import cached_property

KINDS = ('initial', 'generated', 'repair')


def symbol(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return int.from_bytes(hashlib.sha256(data).digest()[:4], 'little') % 8192


class Catalog:
    @cached_property
    def connected_orders(self):
        orders={}
        for rid,atoms in self.atoms.items():
            for anchor in range(len(atoms)):
                picked=[anchor]
                remaining=[i for i in range(len(atoms)) if i!=anchor]
                while remaining:
                    # Keep source order among atoms linked to the named prefix.
                    # A disconnected component starts in source order as well.
                    nxt=next((i for i in remaining if any(self.field_links[rid,j,i] for j in picked)),
                             remaining[0])
                    remaining.remove(nxt)
                    picked.append(nxt)
                orders[rid,anchor]=tuple(picked)
        return orders

    def read_order(self,rid,anchor,mode):
        if mode=='connected':
            return self.connected_orders[rid,anchor]
        if mode=='source':
            return (anchor,*(i for i in range(len(self.atoms[rid])) if i!=anchor))
        raise ValueError('unknown pointer read order')

    def __init__(self, program):
        recipe = program['recipe']
        self.tables = {t['name']: i for i, t in enumerate(recipe['tables'])}
        self.nodes, self.edges = [], []
        self.outputs, self.inputs, self.atoms, self.roots = {}, {}, {}, {}
        self.field_links = {}
        self.seminaive = [r['metadata']['seminaive'] for r in recipe['rules']]
        merges = {m['table']: m for m in program['merge_programs']['programs']}

        for name, tid in self.tables.items():
            tmpl = ('initial', tid)
            self.roots[tmpl] = self.node(('input', name))
            self.outputs[tmpl, 0] = self.roots[tmpl]
        for name, merge in merges.items():
            tmpl = ('repair', self.tables[name])
            root = self.node(('merge', merge['equal_inputs']))
            self.roots[tmpl] = root
            self.merge_block(merge, root, tmpl, 0)
        for rid, rule in enumerate(recipe['rules']):
            tmpl = ('generated', rid)
            root = self.node('rule')
            self.roots[tmpl] = root
            slots = [self.slot_node(('slot', s['sort']['kind']), s['sort']) for s in rule['slots']]
            atoms = []
            for atom in rule['query']:
                n = self.operation(root, slots, atom, 'query')
                if 'table' in atom['call']:
                    atoms.append((self.tables[atom['call']['table']], n))
            slots_by_atom = [tuple(arg.get('slot') for arg in atom['args'])
                             for atom in rule['query'] if 'table' in atom['call']]
            for previous, source in enumerate(slots_by_atom):
                for current, target in enumerate(slots_by_atom):
                    if previous != current:
                        self.field_links[rid, previous, current] = [
                            (a, b) for a, x in enumerate(source) for b, y in enumerate(target)
                            if x is not None and x == y]
            self.atoms[rid] = atoms
            self.inputs[tmpl] = [n for _, n in atoms]
            offset = len(rule['effects'])
            for pc, effect in enumerate(rule['effects']):
                n = self.operation(root, slots, effect, effect['op'])
                self.outputs[tmpl, pc] = n
                table = effect.get('call', {}).get('table')
                if effect['op'] == 'set' and table in merges:
                    self.merge_block(merges[table], n, tmpl, offset)
                    offset += len(merges[table]['operations'])

    def slot_node(self, label, sort):
        return self.node(label)

    def node(self, label):
        idx = len(self.nodes)
        self.nodes.append(symbol(label))
        return idx

    def link(self, a, b, role):
        self.edges.extend(((a, b, role * 2), (b, a, role * 2 + 1)))

    def operand(self, slots, arg):
        return slots[arg['slot']] if 'slot' in arg else self.node(('literal', arg))

    def operation(self, root, slots, op, kind):
        n = self.node((kind, op.get('call'), op.get('kind')))
        self.link(root, n, 0)
        args = op.get('args', []) + [op[k] for k in ('arg', 'value') if k in op]
        for i, arg in enumerate(args):
            self.link(self.operand(slots, arg), n, i + 2)
        if 'dst' in op:
            self.link(n, slots[op['dst']], 1)
        return n

    def merge_block(self, merge, root, tmpl, offset):
        slots = [self.slot_node(('operand', role if role < 2 else 'internal', s['kind']), s)
                 for role, s in enumerate(merge['slots'])]
        if tmpl[0] == 'repair':
            self.inputs[tmpl] = slots[:2]
        for pc, op in enumerate(merge['operations']):
            n = self.operation(root, slots, op, 'merge-op')
            self.outputs[tmpl, offset + pc] = n
        self.link(self.operand(slots, merge['result']), root, 1)
