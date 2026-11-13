import unittest
from analyze_rhs_routes import analyze


def fixture(effect=3, residual=()):
    program = dict(sha256='p', multi_stage=dict(routes=[dict(producer=4, effect=effect, consumer=5, residual=list(residual))]))
    b = dict(cell=10, rule=5, operation=0, run=3, previous_run=2, previous_rule=6,
             prior_status='visible', facts=0, success=True, forwarded=False,
             receipt={'Fact': dict(cell=7, op=3)})
    trace = dict(dropped=0, boundary_dropped=0, boundaries=[b],
                 events=[dict(cell=7, rule=4, run=1)], plans=[None]*4+[dict(constructor_sites=1)])
    audit = dict(program_sha256='p', runs=3, all_saved_run_checks_equal=True,
                 rhs_projection_trace=dict(complete_archive=True, trace=trace))
    return program, audit


class RouteTests(unittest.TestCase):
    def test_compact_routes_derive_residual_from_consumer_query(self):
        p, a = fixture()
        route = p['multi_stage']['routes'][0]
        del route['residual']
        route.update(anchor=0, steps=[dict(atom=1)])
        p['recipe'] = dict(rules=[dict(query=[])]*5+[dict(query=[{},{}])])
        self.assertEqual(analyze(p,a)['counts']['exact_effect_entry_without_residual'],1)
        p['recipe']['rules'][5]['query'].append({})
        self.assertEqual(analyze(p,a)['counts']['exact_effect_entry_without_residual'],0)

    def test_physical_owner_not_last_reuser(self):
        r = analyze(*fixture())
        self.assertEqual(r['counts']['exact_effect_entry_without_residual'], 1)
        self.assertEqual(r['routes'][0]['producer'], 4)

    def test_other_effect_route_and_residual_are_not_completion(self):
        self.assertEqual(analyze(*fixture(effect=8))['counts']['exact_effect_entry_present'], 0)
        self.assertEqual(analyze(*fixture(residual=[2]))['counts']['exact_effect_entry_without_residual'], 0)

    def test_missing_owner_is_unknown_and_mismatched_program_rejected(self):
        p, a = fixture()
        a['rhs_projection_trace']['trace']['events'] = []
        self.assertEqual(analyze(p, a)['counts']['owner_not_in_completion_archive'], 1)
        p['sha256'] = 'other'
        with self.assertRaises(ValueError): analyze(p, a)


if __name__ == '__main__': unittest.main()
