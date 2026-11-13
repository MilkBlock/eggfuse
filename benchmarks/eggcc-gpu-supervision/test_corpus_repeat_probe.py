import unittest
import numpy as np
from corpus_repeat_probe import wiring,attachment,numerical_audit,scale_report
from corpus_cell_ridge import initial_attachment
from boundary_cell_ridge import D,B
from dominator_completion import compose
from test_cell_token_successors import rule,atom,make,TABLES


class Repeat(unittest.TestCase):
    def test_fixed_wiring_consumes_current_not_initial_channels(self):
        ports=[('input',0),('input',1)];binding=[(0,ports[0]),(1,ports[1]),(2,ports[0])]
        indices,mix=wiring(ports,binding,4)
        values=np.random.default_rng(3).normal(size=D+2*B).astype(np.float32)
        for offset in [0.,.4]:
            updated=values.copy();updated[D:]+=offset
            np.testing.assert_allclose(attachment(updated[None,:],indices[None,:],mix[None,:],np)[0],initial_attachment(updated,ports,binding),atol=1e-6)

    def test_completed_constructor_binding_adds_nothing_when_repeated(self):
        a,b=('input',0),('input',1);source=[('F',(a,b))]
        consumer=rule([atom('F',0,1)],[make('G',2,1)],2)
        first,reason=compose(source,consumer,[(0,a),(1,b)],TABLES)
        self.assertIsNone(reason);self.assertTrue(first['novel'])
        mapping=dict(first['source_map'])
        second,reason=compose(first['facts'],consumer,[(0,mapping[a]),(1,mapping[b])],TABLES)
        self.assertIsNone(reason);self.assertFalse(second['novel'])

    def test_numerical_failures_are_reported_without_relaxing_tolerance(self):
        result=numerical_audit(np.array([[.01]]),np.array([[0.]]),np.array([[True]]),np.array([[False]]))
        self.assertFalse(result['passed']);self.assertEqual(result['state_elements_outside_tolerance'],1);self.assertEqual(result['emission_disagreements'],1)

    def test_nonfinite_values_fail_even_when_both_backends_agree(self):
        for value in (np.nan,np.inf,-np.inf):
            result=numerical_audit(np.array([[value]]),np.array([[value]]),np.array([[False]]),np.array([[False]]))
            self.assertFalse(result['passed'])
            self.assertEqual(result['nonfinite_state_elements'],1)
            self.assertIsNone(result['max_absolute_state_difference'])

    def test_nonfinite_scale_reports_are_json_safe(self):
        import json
        result=scale_report([[np.inf,np.nan,3]])
        self.assertEqual(result,[dict(body_max_abs=None,boundary_max_abs=None,boundary_coordinates_outside_teacher_range=3)])
        json.dumps(result,allow_nan=False)

if __name__=='__main__':unittest.main()
