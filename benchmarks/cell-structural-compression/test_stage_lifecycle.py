import unittest
from analyze_stage_lifecycle import analyze

class LifecycleTest(unittest.TestCase):
    def sample(self):
        fact = dict(epoch=7, born=3, hidden=False, owned=True,
                    local_union_owned=False, entry=None, decoded=False)
        return dict(program_sha256='test', runs=2, graph_owned_teardown_bytes=1000,
            ownership_storage=dict(components=[dict(id=1, frames=[1, 2])]),
            source_storage=dict(fact_lifecycle=dict(epoch_pair_bytes=16, frames=[
                dict(cell=1, template=0, completed=True, started_epoch=3, facts=[dict(fact), dict(fact)]),
                dict(cell=2, template=1, completed=True, started_epoch=7, facts=[dict(fact)])])))

    def test_cross_frame_is_subset(self):
        r = analyze(self.sample())['totals']
        self.assertEqual(r['epoch_pair_gross_upper_bound_bytes'], 32)
        self.assertEqual(r['cross_frame_extra_gross_upper_bound_bytes'], 16)

    def test_visibility_and_birth_split_cohorts(self):
        d = self.sample()
        facts = d['source_storage']['fact_lifecycle']['frames']
        facts[0]['facts'][1]['hidden'] = True
        facts[1]['facts'][0]['born'] = 4
        self.assertEqual(analyze(d)['totals']['cohorts'], 3)
        self.assertEqual(analyze(d)['totals']['epoch_pair_gross_upper_bound_bytes'], 0)

    def test_no_owner_does_not_merge_unrelated_frames(self):
        d = self.sample(); d['ownership_storage']['components'] = []
        self.assertEqual(analyze(d)['totals']['epoch_pair_gross_upper_bound_bytes'], 16)
        self.assertEqual(analyze(d)['totals']['cross_frame_extra_gross_upper_bound_bytes'], 0)

if __name__ == '__main__':
    unittest.main()
