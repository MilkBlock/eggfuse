import unittest

from bake import BASE,CONG,EDGE,FLIP,JOIN,LOCAL,REFL,bake,plans,prove


class CertificateContract(unittest.TestCase):
    def test_congruence_requires_ordered_operand_witnesses(self):
        plan=dict(vertices=6,public=[[0,1,2],[3,4,5]],local_pair=[0,1],
                  implications=[dict(requires=[[0,3],[1,4]],unifies=[2,5])])
        edge=EDGE*BASE
        second=[LOCAL*BASE,FLIP*BASE,edge,JOIN*BASE,LOCAL*BASE+1,JOIN*BASE]
        self.assertEqual(prove(plan,[edge,*second,CONG*BASE]),(2,5,3,1))
        with self.assertRaises(ValueError):prove(plan,[*second,edge,CONG*BASE])

    def test_wrong_composition_and_unknown_constructor(self):
        plan=plans()['rule-266']
        with self.assertRaises(ValueError):prove(plan,[REFL*BASE,1,JOIN*BASE])
        with self.assertRaises(ValueError):prove(plan,[CONG*BASE+250])

    def test_no_unconditional_cross_owner_macro(self):
        for plan in plans().values():
            bank=bake(plan)
            for i in range(6):
                for j in range(6):
                    self.assertEqual(bank['routes'][i*6+j]>=0,i==j)
