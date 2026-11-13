import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from test_device_join_transition import fixture,device_plan
from test_device_query_join import fixture as query_fixture
from device_join_transition import step,run_round
from device_match_capture import audit,host,floating_inputs


class MatchCapture(unittest.TestCase):
    def test_capture_uses_same_joint_match_without_changing_admission(self):
        recipe,_=query_fixture();s,p,m=fixture()
        out,marks=step(s,p,m,4,True,True,np,capture=True)
        plain,pm=step(s,p,m,4,True,True,np)
        for key in out:np.testing.assert_array_equal(out[key],plain[key])
        self.assertNotIn('capture',pm)
        cap=marks['capture'];check=audit(recipe,cap)
        self.assertTrue(check['passed'],check);self.assertEqual(check['checked'],1)
        self.assertEqual(check['accepted'],1)
        lane=np.flatnonzero(cap['bindings']['live'])[0]
        self.assertEqual(cap['bindings']['witness_rows'][lane].tolist(),[0,1])
        inputs=floating_inputs(cap,m,np)
        np.testing.assert_allclose(np.tanh(inputs@m['coef'])[lane],cap['predicted_tokens'][lane],atol=2e-6)

    def test_joint_conflict_generation_and_port_corruption_are_rejected(self):
        recipe,_=query_fixture();s,p,m=fixture();_,marks=step(s,p,m,4,True,True,np,capture=True)
        for mode in ('join','generation','port','record'):
            c=deepcopy(marks['capture']);i=np.flatnonzero(c['bindings']['live'])[0]
            if mode=='join':c['witness']['slot_roots'][i,1,0]=777
            elif mode=='generation':c['witness']['generation'][i,1]+=1
            elif mode=='port':c['source_ports'][i,0]=999
            else:c['bindings']['witness_records'][i,0]=999
            self.assertFalse(audit(recipe,c)['passed'],mode)

    def test_compiled_gpu_captures_real_input_and_shared_owner_reads(self):
        from device_slot_owners import pack
        recipe,_=query_fixture();s,p,m=fixture();s=pack(s)
        dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        ds,dm=dev(s),dev(m);dp=device_plan(p)
        out,marks=mx.compile(lambda state:step(state,dp,dm,4,mx.array(True),mx.array(True),mx,capture=True))(ds)
        mx.eval(out,marks);c=host(marks['capture'])
        self.assertTrue(audit(recipe,c)['passed'])
        broken=deepcopy(c);lane=np.flatnonzero(c['bindings']['live'])[0]
        broken['witness']['physical_generation'][lane,0]+=1
        self.assertFalse(audit(recipe,broken)['passed'])
        live=c['bindings']['live'];expected=np.tanh(floating_inputs(c,m,np)@m['coef'])
        np.testing.assert_allclose(c['predicted_tokens'][live],expected[live],atol=2e-6)

    def test_capture_partition_requires_unique_verified_recipe(self):
        import json,tempfile
        from pathlib import Path
        from device_match_capture import partition
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);program=root/'program.json';manifest=root/'manifest.json'
            program.write_text(json.dumps(dict(sha256='fingerprint',recipe={'rules':[]})))
            entry=dict(program_sha256='fingerprint',program=str(program),case='example',status='complete',split='test')
            manifest.write_text(json.dumps(dict(cases=[entry])))
            trace=dict(program_sha256='fingerprint',recipe={'rules':[]})
            self.assertEqual(partition(trace,manifest)['partition'],'test')
            with self.assertRaises(ValueError):partition(dict(trace,recipe={'rules':[1]}),manifest)
            manifest.write_text(json.dumps(dict(cases=[entry,entry])))
            with self.assertRaises(ValueError):partition(trace,manifest)

    def test_disabled_stage_capture_is_not_an_execution_sample(self):
        s,p,m=fixture();_,marks=run_round(s,[(0,p)],m,np.array(1),np,capacity=4,external_complete=True,eq_settled=True,capture=True)
        self.assertFalse(marks['captures'][0]['enabled'])
        self.assertFalse(marks['captures'][0]['accepted'].any())

if __name__=='__main__':unittest.main()
