"""On-device work-path and exact masked-publication checks for Figure 06."""
import json
import os
from pathlib import Path
import sys
import unittest

import torch

from gate_model import GateSystem, TorchStage
from gate_data import templates, INPUTS
from metal_stage import prepare_metal_stage, metal_library
from eclass_ablation.data import dataset
from encoder import EClassSchema


class MetalRowBody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not torch.backends.mps.is_available() or os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0') != '0':
            raise RuntimeError('on-device tests require Metal with fallback disabled')
        torch.manual_seed(107)
        cls.dev = torch.device('mps')
        train = [t for t in templates() if t['split']=='train']
        t = train[0]
        schema = EClassSchema(train)
        cls.model = GateSystem(schema,1703)
        weights=os.environ.get('GATE_TEST_PARENT')
        if weights:
            cls.model.load_actor(torch.load(weights,map_location='cpu',weights_only=True))
        cls.model.to(cls.dev).eval()
        source=dataset('train',t,16)
        cls.inputs=tuple(torch.as_tensor(source[key],dtype=torch.int32,device=cls.dev) for key in INPUTS)
        with torch.inference_mode():
            cls.table=cls.model.encoder.encode_bank(schema.bank(t,'pairwise',cls.dev))

    @torch.inference_mode()
    def test_all_open_vs_original_actor(self):
        original,token,relation=self.model.actor(*self.inputs,self.table,rows=2)
        for backend in ('metal_dense','metal_skip'):
            stages,emitted,pred=self.model(*self.inputs,self.table,mode='all',backend=backend,audit=True)
            for expected,actual in zip(original,stages):
                for key in ('active','pointers','rows','fields'):
                    torch.testing.assert_close(actual[key],expected[key],atol=0,rtol=0)
                for key in ('hidden','active_logits','left_logits','right_logits'):
                    torch.testing.assert_close(actual[key],expected[key],atol=1e-4,rtol=4e-4)
                self.assertTrue(torch.all(actual['executed']==1).item())
                self.assertTrue(torch.all(actual['work_checksum']>0).item())
            torch.testing.assert_close(token,emitted,atol=1e-4,rtol=4e-4)
            torch.testing.assert_close(relation,pred,atol=1e-4,rtol=4e-4)

    @torch.inference_mode()
    def test_closed_reopened_and_independent_graph_lanes(self):
        shape=(len(self.inputs[0]),2,2,4)
        overrides=torch.arange(len(self.inputs[0])*16,device=self.dev).reshape(shape)%5<3
        results={}
        for backend in ('dense','metal_dense','metal_skip'):
            results[backend]=self.model(*self.inputs,self.table,gate_override=overrides,backend=backend,audit=True)
        for run in range(2):
            mask=overrides[:,run].flatten(1,2)
            dense=results['metal_dense'][0][run];physical=results['metal_skip'][0][run]
            torch.testing.assert_close(dense['executed'],torch.ones_like(dense['executed']))
            torch.testing.assert_close(physical['executed'],mask.int())
            self.assertTrue(torch.all(dense['work_checksum'][~mask]>0).item())
            self.assertTrue(torch.all(physical['work_checksum'][~mask]==0).item())
            for k in ('active','pointers','rows','fields','active_logits','left_logits','right_logits','hidden'):
                torch.testing.assert_close(dense[k],physical[k],rtol=0,atol=0)
                self.assertTrue(torch.all(dense[k][~mask]==0).item())
            for k in ('active','pointers','rows','fields'):
                torch.testing.assert_close(dense[k],results['dense'][0][run][k],rtol=0,atol=0)
        token=results['metal_skip'][1]
        self.assertTrue(torch.all(token[~overrides[:,0].flatten(1,2)]==0).item())
        torch.testing.assert_close(results['metal_dense'][1],token,rtol=0,atol=0)
        for backend in ('metal_dense','metal_skip'):
            plain=self.model(*self.inputs,self.table,gate_override=overrides,backend=backend,audit=False)
            for s,t in zip(plain[0],results[backend][0]):
                for key in ('active','pointers','rows','fields'):
                    torch.testing.assert_close(s[key],t[key],rtol=0,atol=0)
                self.assertNotIn('executed',s);self.assertNotIn('work_checksum',s)
            torch.testing.assert_close(plain[1],results[backend][1],rtol=0,atol=0)

    @torch.inference_mode()
    def test_closed_poison_body_and_literal(self):
        dec=self.model.actor.decoder;batch=3;left=torch.randint(5,(batch,6,4),device=self.dev,dtype=torch.int32)
        right=torch.randint(5,(batch,2,2),device=self.dev,dtype=torch.int32)
        lf,rf=dec._source(left),dec._source(right)
        ports=torch.randn(batch,2,32,device=self.dev);routes=[(2,-7),(0,3),(1,0)]
        plan=prepare_metal_stage(dec,left,right,lf,rf,ports,routes)
        ref=TorchStage(dec,left,right,lf,rf,ports,routes)
        gate=torch.tensor([[1,0],[0,1],[1,0]],device=self.dev,dtype=torch.bool)
        prev=torch.randn(batch,2,dec.token_width,device=self.dev)
        poisoned=torch.where(gate[:,:,None],prev,float('nan'))
        results={k:plan.step(1,gate,poisoned,physical=k,audit=True) for k in (False,True)}
        torch.testing.assert_close(results[False][1],results[True][1],rtol=0,atol=0)
        self.assertTrue(torch.isnan(results[False][0]['work_checksum'][~gate]).all().item())
        self.assertTrue(torch.isfinite(results[True][0]['work_checksum']).all().item())
        self.assertTrue(torch.all(results[True][0]['rows'][...,0][gate]==-7).item())
        self.assertTrue(torch.all(results[True][1][~gate]==0).item())
        stage,token=ref.step(1,gate,prev,audit=True)
        torch.testing.assert_close(results[True][1],token,atol=1e-4,rtol=4e-4)
        torch.testing.assert_close(results[True][0]['pointers'],stage['pointers'])
        self.assertEqual(metal_library().score_physical.thread_execution_width,32)


if __name__=='__main__':
    torch.set_num_threads(1)
    unittest.main()
