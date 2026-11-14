import unittest
from collect_boundary_training import select_boundary


class BoundarySelection(unittest.TestCase):
    def fixture(self):
        return dict(reference_execution_seconds=.1,runs=[
            dict(ordinal=4,audit=dict(bindings=[dict(rule=293)])),
            dict(ordinal=5,audit=dict(bindings=[dict(rule=290)])),
            dict(ordinal=6,audit=dict(bindings=[dict(rule=290)]*20))])

    def test_pre_first_continuation_not_largest_future_batch(self):
        self.assertEqual(select_boundary(self.fixture()),4)

    def test_unsupported_or_long_reference_rejected(self):
        for seconds in (None,-1,1.001,float('nan')):
            trace=self.fixture();trace['reference_execution_seconds']=seconds
            with self.assertRaises(ValueError):select_boundary(trace)
        with self.assertRaises(ValueError):select_boundary(self.fixture(),999)

    def test_missing_preceding_run_rejected(self):
        trace=self.fixture();trace['runs'][1]['ordinal']=0
        with self.assertRaises(ValueError):select_boundary(trace)

if __name__=='__main__':unittest.main()
