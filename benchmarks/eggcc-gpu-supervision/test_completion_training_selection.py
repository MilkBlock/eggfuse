import hashlib,json,unittest
from select_completion_training import inspect_case
from collect_boundary_training import select_boundary


class CompletionTrainingSelection(unittest.TestCase):
    def fixture(self):
        trace=dict(program_sha256='p',reference_execution_seconds=.2,strict_audit_reference_equal=True,run_control_counts_equal=True,
            runs=[dict(ordinal=4,audit=dict(bindings=[dict(rule=293)])),dict(ordinal=5,audit=dict(bindings=[dict(rule=290),dict(rule=283)]))])
        raw=json.dumps(trace).encode()
        case=dict(case='training',split='train',status='complete',program_sha256='p',trace_sha256=hashlib.sha256(raw).hexdigest())
        return case,trace,raw

    def test_actual_target_coverage_and_requested_boundary(self):
        c,t,raw=self.fixture();r=inspect_case(c,raw)
        self.assertEqual(r['status'],'eligible');self.assertEqual(r['rule_counts'],{283:1,290:1,293:1})
        self.assertEqual(select_boundary(t),4);self.assertEqual(select_boundary(t,293),3)

    def test_validation_bad_provenance_and_long_cases_rejected(self):
        c,t,raw=self.fixture()
        with self.assertRaises(ValueError):inspect_case(dict(c,split='validation'),raw)
        with self.assertRaises(ValueError):inspect_case(dict(c,trace_sha256='bad'),raw)
        t['reference_execution_seconds']=1.01;raw=json.dumps(t).encode();c['trace_sha256']=hashlib.sha256(raw).hexdigest()
        self.assertEqual(inspect_case(c,raw)['status'],'too_slow')
        t['strict_audit_reference_equal']=False;raw=json.dumps(t).encode();c['trace_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):inspect_case(c,raw)

if __name__=='__main__':unittest.main()
