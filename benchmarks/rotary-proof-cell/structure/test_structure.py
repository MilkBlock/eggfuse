import unittest
import numpy as np
from spec import *
from semantics import labels, expected, teacher_eq, checker_eq

class StructureContracts(unittest.TestCase):
    def test_disjoint_partitions_and_primitive_support(self):
        m=manifest()
        self.assertTrue(all(not x['unseen_input_features'] for x in m['primitive_support']))
        train_layouts={tuple(layout_for(MAPS[i])) for i in TRAIN_MAPS}
        held_layouts={tuple(layout_for(MAPS[i])) for i in HELD_MAPS}
        self.assertFalse(train_layouts&held_layouts)
        for col in range(2):
            self.assertTrue({MAPS[i][col] for i in HELD_MAPS}<={MAPS[i][col] for i in TRAIN_MAPS})
            self.assertTrue({UNIONS[i][col] for i in TEST_UNIONS}<={UNIONS[i][col] for i in TRAIN_UNIONS})

    def test_two_independent_closure_implementations(self):
        for shape in range(len(SHAPES)):
            for union in range(len(UNIONS)):
                for enabled in (0,1):
                    c=[shape,union,0,enabled,6,7,5]
                    for stage in (1,2,3):
                        np.testing.assert_array_equal(teacher_eq(c,stage),checker_eq(c,stage))

    def test_teacher_against_checker_headers(self):
        rng=np.random.default_rng(123)
        for group in GROUPS:
            for case in sample(group,20,rng):
                for stage,h in enumerate(labels(case),1):self.assertEqual(h,expected(case,stage))

    def test_transitive_congruence_and_no_injectivity(self):
        # Parallel chains: a=b -> F(a)=F(b) -> F(F(a))=F(F(b)).
        c=[1,UNIONS.index((0,1)),0,1,6,7,3]
        self.assertTrue(checker_eq(c,2)[6,7]);self.assertFalse(checker_eq(c,1)[6,7])
        # Union of constructor outputs must never imply equality of arguments.
        c[1]=UNIONS.index((4,5))
        self.assertFalse(checker_eq(c,2)[0,1]);self.assertTrue(checker_eq(c,2)[6,7])

    def test_noncommuting_mapping(self):
        self.assertNotEqual(layout_for((1,2)),layout_for((2,1)))
        self.assertEqual(layout_for((0,3)),layout_for((3,0)))

    def test_input_has_no_oracle_and_right_width(self):
        c=sample('joint',7,np.random.default_rng(1))
        self.assertEqual(seed_inputs(c).shape,(7,INPUT_WIDTH))

if __name__=='__main__':unittest.main()
