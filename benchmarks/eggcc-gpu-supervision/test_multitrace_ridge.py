import copy
import unittest
import numpy as np
import mlx.core as mx
from multitrace_ridge import combine
from calibrated_ridge import typed_roles, structured_encode
from context_ridge import prepare
from test_calibrated_ridge import fixture


class Multitrace(unittest.TestCase):
    def test_workload_roots_are_isolated_and_compiler_roles_are_shared(self):
        source=fixture();source['steps']=[dict(ordinal=1,epoch=1)]
        merged,ranges=combine([source,source])
        self.assertEqual(ranges,[(0,1),(1,2)])
        self.assertEqual(source['runs'][0]['audit']['bindings'][0]['rule'],0)
        a,records,_,_=prepare(merged)
        self.assertTrue(set(a['roots'][:2]).isdisjoint(a['roots'][2:]))
        roles=typed_roles(merged,normalize_effects=True)
        np.testing.assert_array_equal(roles[:2],roles[2:])
        self.assertEqual([r['rule'] for r in records],[0,1])

    @unittest.skipUnless(mx.metal.is_available(),'Metal required')
    def test_other_workload_values_and_labels_do_not_change_target_features(self):
        source=fixture();source['steps']=[dict(ordinal=1,epoch=1)]
        other=copy.deepcopy(source)
        other['runs'][0]['audit']['bindings'][0]['values']=[dict(slot=2,value=dict(sort='i64',value=1234))]
        other['runs'][0]['audit']['bindings'][0]['eq_ports'][1]['after']=999
        rng=np.random.default_rng(803)
        w=[mx.array(rng.normal(0,.1,(i,j)).astype(np.float32)) for i,j in [(16,32),(32,64),(32,64),(256,256)]]
        def feature(t):
            merged,_=combine([t,source]);a,records,nroots,_=prepare(merged)
            ga={k:mx.array(a[k]) for k in ('owners','roots','local_roots','roles','scalars','left','right','pair_owner')}
            return np.array(structured_encode(ga,mx.array(typed_roles(merged,normalize_effects=True)),nroots,len(records),w))[-1]
        mx.set_default_device(mx.gpu)
        np.testing.assert_array_equal(feature(source),feature(other))

if __name__=='__main__':unittest.main()
