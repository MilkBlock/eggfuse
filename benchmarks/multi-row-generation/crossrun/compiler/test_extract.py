"""Regression checks for slot provenance and rejecting omitted LHS/RHS effects."""
import copy
import json
import unittest
from pathlib import Path

from extract import lower_rule


class DirectRecipe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recorded = json.loads((Path(__file__).parent/'test-recipe.json').read_text())
        cls.rule = recorded['rule']
        cls.tables = {t['name']:t for t in recorded['tables']}

    def test_output_order_comes_from_effect(self):
        changed = copy.deepcopy(self.rule)
        changed['effects'][0]['args'].reverse()
        original = lower_rule(self.rule, self.tables)
        swapped = lower_rule(changed, self.tables)
        self.assertEqual(swapped['outputs'], list(reversed(original['outputs'])))
        self.assertEqual(swapped['equalities'], original['equalities'])

    def test_reject_computed_output(self):
        changed = copy.deepcopy(self.rule)
        changed['effects'][0]['args'][0] = {'literal': 0}
        with self.assertRaisesRegex(ValueError, 'direct slot'):
            lower_rule(changed, self.tables)

    def test_reject_primitives_and_extra_effects(self):
        extra = copy.deepcopy(self.rule)
        extra['effects'].append({'op':'union'})
        primitive = copy.deepcopy(self.rule)
        primitive['interface']['primitive_atoms'].append(2)
        for changed in (extra, primitive):
            with self.assertRaises(ValueError):
                lower_rule(changed, self.tables)


if __name__ == '__main__':
    unittest.main()
