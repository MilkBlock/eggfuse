"""Compose scalar preparation across an existing constructor-to-query interface.

This never authorizes query completion, mutable reads or graph effects. A consumer
reads prepared columns only after its ordinary match and lifetime checks succeed.
"""
import copy
from compiler import Affine, Unsupported


def scalar(slot):
    return slot['sort']['kind'] == 'i64'


class Continuation:
    def __init__(self, producer, consumer, operation, atom, table, bound=1 << 20):
        out = producer['effects'][operation]
        if table.get('kind') != 'constructor' or out.get('call', {}).get('table') != table.get('name'):
            raise Unsupported('boundary is not a declared constructor')
        entry = consumer['query'][atom]
        if out.get('kind') not in ('construct', 'set') or out.get('call') != entry.get('call'):
            raise Unsupported('not a constructor-to-query interface')
        # Require constructor sort, never a mutable function write.
        result_slot = out.get('dst') if out.get('kind') == 'construct' else out.get('value', {}).get('slot')
        if result_slot is None or producer['slots'][result_slot]['sort']['kind'] != 'eq':
            raise Unsupported('mutable or untyped boundary')
        result = {'slot': result_slot}
        row = out['args'] + [result]
        if len(row) != len(entry['args']):
            raise Unsupported('interface arity')
        self.wiring = {}
        for target, source in zip(entry['args'], row):
            if 'slot' not in target:
                # A differing literal would require a runtime condition.
                if target != source:
                    raise Unsupported('unproved literal constraint')
                continue
            slot = target['slot']
            sort = consumer['slots'][slot]['sort']['kind']
            source_sort = (producer['slots'][source['slot']]['sort'] if 'slot' in source else source['sort'])['kind']
            if sort != source_sort:
                raise Unsupported('interface sort')
            if slot in self.wiring and self.wiring[slot] != source:
                raise Unsupported('unproved shared slot constraint')
            self.wiring[slot] = source
        self.offset = len(producer['slots'])
        slots = copy.deepcopy(producer['slots'] + consumer['slots'])
        effects = []
        for op in producer['effects']:
            if op.get('kind') == 'compute' or (op.get('op') == 'copy' and op.get('sort', {}).get('kind') == 'i64'):
                effects.append(copy.deepcopy(op))
        for i, slot in enumerate(consumer['slots']):
            if scalar(slot) and slot['definition'] == 'query':
                if i not in self.wiring:
                    raise Unsupported('late scalar input')
                effects.append(dict(op='copy', kind='copy', dst=i+self.offset,
                                    sort=slot['sort'], arg=copy.deepcopy(self.wiring[i])))
        for original in consumer['effects']:
            if original.get('kind') == 'compute' or (original.get('op') == 'copy' and original.get('sort', {}).get('kind') == 'i64'):
                op = copy.deepcopy(original)
                op['dst'] += self.offset
                for arg in op.get('args', [op.get('arg', {})]):
                    if 'slot' in arg:
                        arg['slot'] += self.offset
                effects.append(op)
        used = {a['slot'] for op in effects for a in op.get('args', [op.get('arg', {})]) if 'slot' in a}
        inputs = [i for i, s in enumerate(producer['slots']) if scalar(s) and s['definition'] == 'query' and i in used]
        self.rule = dict(slots=slots, effects=effects)
        # Conservatively preserve every computed result: boundary graph effects,
        # history or additional consumers may need any of them.
        self.plan = Affine(self.rule, inputs, [bound] * len(inputs))
        self.stage_columns = [
            {op['dst']: self.plan.output_columns[op['dst'] + shift]
             for op in rule['effects'] if op.get('kind') == 'compute'}
            for rule, shift in [(producer, 0), (consumer, self.offset)]
        ]
        self.consumer_input_columns = {
            dst: self.plan.output_columns[src['slot']]
            for dst, src in self.wiring.items()
            if 'slot' in src and src['slot'] in self.plan.output_columns
            and scalar(consumer['slots'][dst])
        }
        self.obligations = ['ordinary consumer match including guards and residual atoms',
                            'source Run publication and visibility',
                            'current instance lifetime and actual constructor witness',
                            'original ordered graph effects; no predicted union or mutation']

    def consumer_column(self, device_results, slot):
        # A view of the retained joint result, not a newly assembled input batch.
        return device_results[:, self.stage_columns[1][slot]]
