import unittest
import numpy as np
from audit_history_policy import categories, compare


class PolicyAudit(unittest.TestCase):
    def test_direct_descendant_and_unaffected(self):
        def node(*sources):
            return dict(target=np.zeros(2),edges=[(s,np.zeros(2)) for s in sources])
        a=[node(),node(),node(0),node(2),node(1)]
        b=[node(),node(),node(1),node(2),node(1)]
        self.assertEqual(categories(a,b),['unchanged','unchanged','direct','descendant','unchanged'])
        a[4]['edge_routes']=[np.zeros(2)]
        b[4]['edge_routes']=[np.ones(2)]
        self.assertEqual(categories(a,b)[4],'direct')
        b[0]=node(4)
        with self.assertRaisesRegex(ValueError,'noncausal'):categories(a,b)

    def test_pair_counts_separate_gains_losses_and_empty(self):
        rows=[dict(pairs=[(0,1)],index=i,rule=1) for i in range(4)]
        rows.append(dict(pairs=[],index=4,rule=2))
        old=[dict(exact=v) for v in [True,True,False,False,False]]
        new=[dict(exact=v) for v in [True,False,True,False,True]]
        out=compare(rows,old,new,['unchanged']*5)
        self.assertEqual(out['by_route']['unchanged'],dict(both_exact=1,lost_exact=1,gained_exact=1,both_wrong=1))
        self.assertNotIn('2',out['by_rule'])


if __name__=='__main__':unittest.main()
