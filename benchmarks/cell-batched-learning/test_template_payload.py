import copy
import unittest
from template_payload import census


class TemplatePayload(unittest.TestCase):
    def setUp(self):
        self.value = (7 << 32) | 1
        self.storage = dict(components=[dict(shape=0, frames=[7], signals=[self.value])],
            shapes=[dict(programs=[0], ports=[[0]])],
            programs=[dict(native={'0': 0}, fields=[[0]])])
        self.frames = [dict(cell=7, facts=[dict(op=0, owned=True, hidden=False)])]

    def test_native_fields_need_no_dynamic_scalars(self):
        c = census(self.storage, self.frames)
        self.assertEqual(c['exact_origin_address_bindings'], 1)
        self.assertEqual(c['facts_without_scalars'], 1)

    def test_foreign_binding_is_not_an_implicit_native_result(self):
        self.storage['components'][0]['signals'][0] = (8 << 32) | 1
        c = census(self.storage, self.frames)
        self.assertEqual(c['other_bindings'], 1)
        self.assertEqual(c['facts_without_scalars'], 1)

    def test_hidden_fact_still_has_storage_obligations(self):
        self.frames[0]['facts'][0]['hidden'] = True
        self.assertEqual(census(self.storage, self.frames)['hidden_facts_without_scalars'], 1)

    def test_unbound_live_field_is_rejected(self):
        self.storage['components'][0]['signals'][0] = None
        with self.assertRaises(ValueError):
            census(self.storage, self.frames)

    def test_missing_or_duplicate_projection_is_rejected(self):
        with self.assertRaises(ValueError):
            census(dict(components=[], shapes=[], programs=[]), self.frames)
        self.storage['components'].append(copy.deepcopy(self.storage['components'][0]))
        with self.assertRaises(ValueError):
            census(self.storage, self.frames)

    def test_later_native_alias_is_not_first_origin_proof(self):
        self.storage['components'][0]['frames'].append(8)
        self.storage['shapes'][0] = dict(programs=[0, 0], ports=[[0], [0]])
        self.storage['components'][0]['signals'][0] = (8 << 32) | 1
        self.assertEqual(census(self.storage, self.frames)['other_bindings'], 1)
