import unittest
import numpy as np
import mlx.core as mx
from test_device_query_join import fixture
from enumerate_cell_interactions import enumerate_interfaces
from synthetic_cell_inputs import digest
from materialize_enumerated_cells import prepare
from device_slot_owners import pack
from device_query_join import compile_query,match
from device_snapshot_import import prepare_family
from audit_snapshot_queries import device

class ProducerFrames(unittest.TestCase):
    def test_matched_inputs_cannot_be_declared_completed(self):
        r,_=fixture()
        for t in r['tables']:t['schema']=[dict(kind='eq',name='E')]*2
        cases,_=enumerate_interfaces(r,6,producer_phase='matched')
        c=cases[0]
        doc=dict(schema='enumerated-cell-input/v1',recipe=r,recipe_sha256=digest(r),case=c,snapshot=c['snapshot'],input_sha256=c['input_sha256'])
        with self.assertRaisesRegex(ValueError,'completed phase'):prepare(doc,4)

    def test_sources_survive_import_and_gpu_match(self):
        r,_=fixture()
        for t in r['tables']:t['schema']=[dict(kind='eq',name='E')]*2
        cases,_=enumerate_interfaces(r,6,producer_count=2)
        cases=[c for c in cases if c['producer']==[0,1] and c['consumer']==2]
        self.assertTrue(cases)
        for c in cases:
            doc=dict(schema='enumerated-cell-input/v1',recipe=r,recipe_sha256=digest(r),case=c,snapshot=c['snapshot'],input_sha256=c['input_sha256'])
            local,state,ids,rows,report=prepare(doc,4)
            self.assertEqual(report['retained_boundary_rows'],0)
            packed=pack(state);plan=compile_query(local,2)
            out=match(packed,plan,8,True,True,np)
            self.assertTrue(out['complete']);self.assertTrue(out['live'].any())
            for row in out['witness_rows'][out['live']]:
                self.assertEqual(set(row),set(report['producer_rows']))
            base,bs,bi,_=prepare_family(r,c['snapshot'],[0,1,2],4)
            reference=match(bs,compile_query(base,2),8,True,True,np)
            def keys(o):return {tuple(x) for x in o['slot_roots'][o['live']]}
            self.assertEqual(keys(out),keys(reference))
        ds,dp=map(device,(packed,plan))
        actual=mx.compile(lambda s:match(s,dp,8,mx.array(True),mx.array(True),mx))(ds);mx.eval(actual)
        np.testing.assert_array_equal(actual['witness_rows'],out['witness_rows'])
        # Physical payload retirement invalidates source availability.
        packed['owner_live'][report['producer_rows'][0]]=False
        retired=match(packed,plan,8,True,True,np)
        self.assertFalse(retired['complete'])

if __name__=='__main__':unittest.main()
