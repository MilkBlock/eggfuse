import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from neural_baked_eq import compile_rule,compile_owner,apply
from device_slot_owners import compile_transfer
from test_neural_cell_chains import recipe


class BakedEq(unittest.TestCase):
    def test_multistep_congruence_and_all_arguments(self):
        eq=dict(kind='eq',name='E')
        def atom(name,*ports):return dict(call=dict(table=name),args=[dict(slot=i) for i in ports])
        r=dict(slots=[dict(sort=eq,definition='query') for _ in range(10)],query=[atom('F',0,2,4),atom('F',1,3,5),atom('G',4,6),atom('G',5,7)],effects=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        rec=dict(tables=[dict(name=t,kind='constructor') for t in ('F','G')],rules=[r])
        pairs=list(zip(*np.triu_indices(10,1)))
        self.assertFalse(compile_rule(rec,r,10)['known'][pairs.index((4,5))])
        r['effects'].append(dict(kind='union',args=[dict(slot=2),dict(slot=3)]))
        proof=compile_rule(rec,r,10);self.assertTrue(proof['supported'])
        self.assertTrue(proof['known'][pairs.index((4,5))]);self.assertTrue(proof['known'][pairs.index((6,7))])
        self.assertFalse(proof['known'][pairs.index((8,9))])
        # Mutable reads do not admit this sealed-constructor proof.
        rec['tables'][0]['kind']='function';self.assertFalse(compile_rule(rec,r,10)['supported'])

    def test_owner_bindings_are_proven_without_instance_values(self):
        r=recipe();p=compile_transfer(r,dict(producer=0,consumer=0,projection=[1,2],projection_valid=[True,True]),6)
        proof=compile_owner(r,p,3);cross=proof['cross_known_eq'].reshape(3,3)
        self.assertTrue(cross[1,0]);self.assertTrue(cross[2,1]);self.assertFalse(cross[0,2])
        self.assertFalse(proof['source_known_eq'].any())
        self.assertFalse(proof['target_known_eq'].any())

    def test_device_overlay_is_positive_only_and_does_not_hide_nan(self):
        score=mx.array([[-4.,2.,float('nan')]])
        out=mx.compile(lambda x:apply(x,mx.array([True,False,True]),mx))(score);mx.eval(out)
        np.testing.assert_array_equal(np.array(out)[:,:2],[[1.,2.]])
        self.assertTrue(np.isnan(np.array(out)[0,2]))


if __name__=='__main__':unittest.main()
