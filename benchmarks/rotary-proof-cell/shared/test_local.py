import unittest
import numpy as np
from abi import *
from fresh import freeze,freeze_final
from spec import shape_key,SHAPES,MAPS,TRAIN_MAPS
from local_supervision import SWAP_LABEL,INSERT_LABEL,RELATION_LABEL,FEATURES

class LocalSupervisionTests(unittest.TestCase):
    def test_final_unseen_shapes(self):
        dev=freeze();final=freeze_final();keys={shape_key(s) for s in final['shapes'][16:]}
        self.assertEqual(len(keys),16)
        self.assertFalse(keys&{shape_key(s) for s in SHAPES[:10]+dev['shapes']})

    def test_primitive_pointer_targets_and_input_coverage(self):
        self.assertEqual({k for i in TRAIN_MAPS for k in MAPS[i]},set(range(7)))
        for k,row in enumerate(SWAP_LABEL):
            for src,dst in enumerate(row):
                self.assertEqual(SWAP_LABEL[k,dst],src)  # involution, not a merged mapping
            self.assertEqual(sorted(row.tolist()),list(range(8)))
        self.assertEqual(INSERT_LABEL.tolist(),[[0,1,2,3,5,6,7,8]])

    def test_basic_rule_labels(self):
        table={tuple(row.astype(int)):int(y) for row,y in zip(FEATURES,RELATION_LABEL)}
        self.assertEqual(table[(0,0,0,0,0,0,0,0)],0)
        self.assertEqual(table[(0,0,1,0,0,0,0,0)],1)
        self.assertEqual(table[(0,0,0,1,0,1,0,0)],0) # binary constructor missing arg2 equality
        self.assertEqual(table[(0,0,0,1,1,1,0,0)],1) # unary only needs arg1
        self.assertEqual(table[(0,0,0,0,0,0,0,1)],1) # transitive witness

if __name__=='__main__':unittest.main()
