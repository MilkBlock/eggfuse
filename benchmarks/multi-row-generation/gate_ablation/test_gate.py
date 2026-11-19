"""Device checks for causal admissions, null token publication and real MPS skipping."""
import json
from pathlib import Path
import unittest

import torch
from gate_model import GateSystem, _fig20
from eclass_ablation.data import dataset
from width_ablation.model import WidthSystem
from encoder import EClassSchema

BASE = Path(__file__).resolve().parents[1] / 'eclass_ablation'


def same(x, y):
    torch.testing.assert_close(x,y,atol=0,rtol=0)


class GateContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not torch.backends.mps.is_available():raise RuntimeError('MPS required')
        ts=json.loads((BASE/'corpus/manifest.json').read_text())['templates']
        trained=[t for t in ts if t['split']=='train']
        schema=EClassSchema(trained);cls.gate=GateSystem(schema,1703)
        checkpoint=Path('/Volumes/EggFuseWorkspace/experiments/two-row-credit-20261119/supervised-1703/final.pt')
        state=torch.load(checkpoint,map_location='cpu',weights_only=True)
        cls.gate.load_actor(state);cls.gate.to('mps').eval()
        cls.original=WidthSystem(schema,1703);cls.original.load_state_dict(state);cls.original.to('mps').eval()
        t=trained[0];x=dataset('train',t,8);bank=schema.bank(t,'pairwise','mps')
        with torch.inference_mode():
            cls.table=cls.gate.encoder.frozen_bank(bank)
        cls.inputs=tuple(torch.as_tensor(x[k],device='mps',dtype=torch.int32) for k in _fig20.INPUTS)

    @torch.inference_mode()
    def test_all_open_matches_frozen_actor(self):
        stages,token,relation=self.gate(*self.inputs,self.table,mode='all',audit=True)
        reference,old_token,old_relation=self.original(*self.inputs,self.table,rows=2)
        same(token,old_token);same(relation,old_relation)
        for row,old in zip(stages,reference):
            for k in old:same(row[k],old[k])
            same(row['pre_active_logits'],old['active_logits'])
            same(row['pre_right_logits'],old['right_logits'])
            self.assertTrue(bool(row['gate_open'].all()))
            self.assertTrue(bool(row['executed'].all()))
        # Existing null decisions retain original hard one-hot and provenance.
        self.assertTrue(bool((stages[0]['active']==0).any()))
        self.assertTrue(bool(token[...,32][stages[0]['active']==0].eq(1).all()))

    @torch.inference_mode()
    def test_close_both_then_reopen_without_old_history(self):
        batch=self.inputs[0].shape[0]
        all_off,empty,_=self.gate(*self.inputs,self.table,mode='none',audit=True)
        same(empty,torch.zeros_like(empty))
        for stage in all_off:
            for k in ('hidden','active_logits','left_logits','right_logits','rows','active','pointers','gate_open'):
                same(stage[k],torch.zeros_like(stage[k]))
            self.assertTrue(bool(stage['pre_active_logits'].abs().sum()>0))
            self.assertTrue(bool(stage['executed'].all()))
        mask=torch.ones((batch,2,2,4),device='mps',dtype=torch.bool);mask[:,:,:,1]=False
        perturbed=mask.clone();perturbed[:,:,:,0]=False
        first,t1,_=self.gate(*self.inputs,self.table,gate_override=mask)
        second,t2,_=self.gate(*self.inputs,self.table,gate_override=perturbed)
        for t in (t1,t2):same(t[:,1::4],torch.zeros_like(t[:,1::4]))
        # make emits one token in each row after that row's previous token was
        # closed, even when an earlier token differs (no stale history retained).
        same(t1[:,2::4],t2[:,2::4]);self.assertTrue(bool(t2[:,2::4].abs().sum()>0))
        for stage in first:
            torch.testing.assert_close(stage['gate_open'],mask[:,0].reshape(batch,8))
        for stage in second:
            self.assertTrue(bool(stage['gate_open'][:,2::4].all()))

    @torch.inference_mode()
    def test_one_slot_intervention_keeps_policy_and_causal_prefix(self):
        batch = self.inputs[0].shape[0]
        nominal, t0, _ = self.gate(*self.inputs, self.table)
        blank = torch.full((batch, 2, 2, 4), -1, device='mps', dtype=torch.int32)
        unchanged, token, _ = self.gate(*self.inputs, self.table, gate_override=blank)
        same(token,t0)
        for a,b in zip(nominal,unchanged):
            for key in a:same(a[key],b[key])
        # One distinct make slot per graph; all other decision bits are evaluated
        # from each trajectory's own state, including later rounds of finish.
        graph = torch.arange(batch, device='mps')
        row = graph % 2
        time = (graph // 2) % 4
        forced = torch.zeros_like(blank, dtype=torch.bool)
        forced[graph, 0, row, time] = True
        outputs = []
        for action in (0,1):
            intervention = torch.where(forced, torch.full_like(blank,action), blank)
            stages, tok, _ = self.gate(*self.inputs,self.table,gate_override=intervention)
            for i, stage in enumerate(stages):
                actual=stage['gate_open'].reshape(batch,2,4)
                expected=torch.where(forced[:,i],bool(action),stage['gate_logits'].reshape(batch,2,4)>=0)
                same(actual,expected)
            outputs.append((stages[0],tok))
        (closed,tclosed),(opened,topen)=outputs
        earlier=(torch.arange(4,device='mps')[None,None,:]<time[:,None,None]).expand(-1,2,-1).reshape(batch,8)
        same(tclosed[earlier],topen[earlier]);same(tclosed[earlier],t0[earlier])
        target=forced[:,0].reshape(batch,8)
        same(closed['gate_logits'][target],opened['gate_logits'][target])
        same(tclosed[target],torch.zeros_like(tclosed[target]));self.assertTrue(bool(topen[target].abs().sum()>0))

    def test_gate_only_gradient_and_threshold(self):
        self.gate.train();self.assertFalse(self.gate.actor.training)
        self.assertFalse(any(p.requires_grad for p in self.gate.actor.parameters()))
        self.gate.zero_grad(set_to_none=True)
        # Clone the cached view outside inference mode to permit autograd use.
        table=self.table.clone()
        stages,_,_=self.gate(*self.inputs,table,mode='all')
        sum(s['gate_logits'].square().mean() for s in stages).backward()
        for g in self.gate.gates:
            self.assertTrue(all(p.grad is not None for p in g.parameters()))
            self.assertGreater(float(g.history.weight.grad.abs().sum()),0)
        self.assertTrue(all(p.grad is None for p in self.gate.actor.parameters()))
        self.gate.eval()
        with torch.inference_mode():
            closed,_,_=self.gate(*self.inputs,self.table,threshold=1)
            opened,_,_=self.gate(*self.inputs,self.table,threshold=0)
        for stage in closed:self.assertFalse(bool(stage['gate_open'].any()))
        for stage in opened:self.assertTrue(bool(stage['gate_open'].all()))

    @torch.inference_mode()
    def test_mixed_open_mask_on_real_metal_paths(self):
        batch=self.inputs[0].shape[0]
        mask=torch.tensor([[[1,0,1,0],[0,0,1,1]],[[0,1,1,1],[1,1,0,1]]],device='mps',dtype=torch.bool).expand(batch,-1,-1,-1)
        dense,dense_token,dense_rel=self.gate(*self.inputs,self.table,gate_override=mask)
        refs=None
        for backend in ('metal_dense','metal_skip'):
            out,tok,rel=self.gate(*self.inputs,self.table,gate_override=mask,backend=backend,audit=True)
            torch.testing.assert_close(tok,dense_token,rtol=3e-4,atol=3e-4)
            torch.testing.assert_close(rel,dense_rel,rtol=3e-4,atol=3e-4)
            for s,(row,original) in enumerate(zip(out,dense)):
                for k in ('active','pointers','rows','gate_open'):same(row[k],original[k])
                expected=mask[:,s].reshape(batch,8) if backend=='metal_skip' else torch.ones_like(mask[:,s].reshape(batch,8))
                same(row['executed'].bool(),expected)
                self.assertTrue(bool(row['work_checksum'][~expected].eq(0).all()))
            if refs is not None:
                prior_t,prior_r=refs;same(tok,prior_t);same(rel,prior_r)
            refs=(tok,rel)


if __name__=='__main__':unittest.main()
