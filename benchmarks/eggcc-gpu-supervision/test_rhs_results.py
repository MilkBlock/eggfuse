import unittest
from summarize_rhs_results import summarize

class RhsResults(unittest.TestCase):
    def fixture(self):
        return dict(schema='eggcc-gpu-supervision-rhs-trace/v1', program_sha256='p',
                    strict_run_graphs_equal=True,strict_audit_reference_equal=True,
                    run_control_counts_equal=True,steps=[{}],runs=[dict(audit=dict(bindings=[dict(
                    values=[dict(slot=0)],rhs=dict(completed=True,slots=[
                        dict(slot=0,value=1),dict(slot=1,value=2,eq_port=dict(at_rhs=2,after_run=1)),
                        dict(slot=2,unavailable='expired')]))]))])
    def test_missing_is_not_success(self):
        r=summarize(self.fixture())
        self.assertEqual(r['counts']['available_slots'],2)
        self.assertEqual(r['counts']['rhs_only_eq_slots'],1)
        self.assertEqual(r['unavailable_slot_fraction'],1/3)
    def test_requires_run_audit(self):
        t=self.fixture();t['strict_run_graphs_equal']=False
        with self.assertRaises(ValueError):summarize(t)

if __name__=='__main__':unittest.main()
