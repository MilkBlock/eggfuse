import unittest
import numpy as np
from neural_follow_round import audit
from reference_union_family import Reference
from device_snapshot_import import identity


class FollowRound(unittest.TestCase):
    def test_audit_rejects_fourth_round_semantic_failure(self):
        from audit_neural_gpu_rhs import audit_failed
        report=dict(pending=False,graph=dict(passed=True),facts_decoded=True,interfaces_preserved=True,token_retained=True,
                    follow=dict(speculation=dict(gpu_installed=1,corrected_graph_pass=1,token_refresh_required=0,
                    downstream_false_positive=0,downstream_missed=0,downstream_incomplete=0,fourth_wrong_states=1)))
        self.assertTrue(audit_failed([report],speculate=True))
        report['follow']['speculation']['fourth_wrong_states']=0
        self.assertFalse(audit_failed([report],speculate=True))

    def test_next_token_errors_and_new_frame_use_are_separate_from_matches(self):
        eq=dict(kind='eq',name='E')
        rule=dict(slots=[dict(sort=eq,definition='query')]*2,
                  query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)])],
                  effects=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        values=[dict(sort='E',eq=str(i)) for i in range(2)]
        ref=Reference(dict(tables=[dict(name='F',kind='constructor',schema=[eq,eq])]),
                      [dict(table='F',values=values)],{identity(v):i for i,v in enumerate(values)})
        result=(dict(inputs=[0,1]),np.array([True]),np.array([[0,1]]),np.array([[-2.]]),
                True,0,np.array([[3]]),np.array([[True]]))
        counts=audit([result],[rule],ref,{0:0,1:1},2,[3])
        self.assertEqual(counts['fourth_missed'],0)
        self.assertEqual(counts['fourth_observed'],1)
        self.assertEqual(counts['fourth_wrong_states'],1)
        self.assertEqual(counts['fourth_consumed_new_frame'],1)
        self.assertEqual(counts['fourth_new_frame_wrong_states'],1)
        self.assertEqual(ref.unions,0)  # CPU supervision cannot modify input state.
        missing=audit([result],[rule],ref,{0:0},2,[3])
        self.assertEqual(missing['fourth_false_positive'],1)
        self.assertEqual(missing['fourth_missed'],1)


if __name__=='__main__':unittest.main()
