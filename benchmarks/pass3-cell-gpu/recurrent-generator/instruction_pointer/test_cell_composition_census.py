import itertools
import unittest
from collections import Counter

from cell_composition_census import operator_ceiling


class OperatorCountTests(unittest.TestCase):
    def test_labeled_roles_indistinguishable_parent_order(self):
        exports=[('A','A','B'),('B','C')]
        rows=[Counter(e) for e in exports]
        for roles in itertools.product('ABC',repeat=3):
            expected=Counter()
            for first,second in itertools.product(range(len(rows)),repeat=2):
                candidates=[[(g,pc) for g,i in enumerate((first,second))
                             for pc,t in enumerate(exports[i]) if t==role] for role in roles]
                for binding in itertools.product(*candidates):
                    if binding[0][0]==0 and any(g==1 for g,_ in binding):expected[2]+=1
            expected[1]=sum(len(list(itertools.product(*[[pc for pc,t in enumerate(e) if t==r] for r in roles])))
                            for e in exports)
            self.assertEqual(operator_ceiling(roles,rows),(expected[1],expected[2]))
