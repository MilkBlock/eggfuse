"""Check the sampled GPU dataflow and exact marginalized credit baselines."""
from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch

import torch

import actor
from actor import CentralCritic, sample_rollout
from width_ablation.model import FIG20, INPUTS, WidthSystem
from eclass_ablation.data import dataset
from encoder import EClassSchema


class CreditContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.device = torch.device(os.environ.get('CREDIT_TEST_DEVICE', 'cpu'))
        ts = json.loads((FIG20/'corpus/manifest.json').read_text())['templates']
        train = [t for t in ts if t['split']=='train']
        schema = EClassSchema(train)
        cls.model = WidthSystem(schema, 1703)
        path = os.environ.get('CREDIT_TEST_PARENT')
        if path:
            cls.model.load_state_dict(torch.load(path, map_location='cpu',weights_only=True))
        cls.model.to(cls.device).eval()
        d = dataset('train', train[0], 8)
        cls.inputs = tuple(torch.as_tensor(d[k], device=cls.device, dtype=torch.int32) for k in INPUTS)
        with torch.no_grad():
            cls.table = cls.model.encoder.encode_bank(schema.bank(train[0], 'pairwise',cls.device))

    def rollout(self, *, greedy=False):
        torch.manual_seed(79)
        return sample_rollout(self.model, self.inputs, self.table, greedy=greedy, epsilon=.04)

    @torch.no_grad()
    def test_original_greedy_and_uniform_mixture_law(self):
        original=self.model(*self.inputs,self.table,rows=2)
        stages,token,relation,records=self.rollout(greedy=True)
        for a,b in zip(stages,original[0]):
            for key in a:
                torch.testing.assert_close(a[key],b[key],rtol=4e-4,atol=4e-5)
        torch.testing.assert_close(token,original[1],rtol=4e-4,atol=4e-5)
        torch.testing.assert_close(relation,original[2],rtol=4e-4,atol=4e-5)
        self.assertEqual(len(records),8)
        sampled,token,_,records=self.rollout()
        for i,rec in enumerate(records):
            run,step=divmod(i,4)
            self.assertEqual((rec.run,rec.step),(run+1,step))
            stage=sampled[run];slots=[step,step+4]
            expected=torch.cat((stage['active'][:,slots,None], stage['pointers'][:,slots]),-1)
            torch.testing.assert_close(expected,rec.action)
            torch.testing.assert_close(rec.other_action,expected.flip(1))
            p=rec.law;c,l,r=rec.action.unbind(-1)
            graph=torch.arange(len(p),device=self.device)[:,None];lane=torch.arange(2,device=self.device)
            torch.testing.assert_close(rec.log_prob.exp(),p[graph,lane,c,l,r],rtol=3e-5,atol=1e-6)
            torch.testing.assert_close(rec.entropy,-(p*p.log()).sum((-3,-2,-1)),rtol=3e-5,atol=1e-6)
            torch.testing.assert_close(p.sum((-3,-2,-1)),torch.ones_like(rec.entropy),rtol=2e-5,atol=1e-6)
            for factor,key in [(p.sum((-2,-1)),'active_logits'),(p.sum((-3,-1)),'left_logits')]:
                logits=stage[key][:,slots];reference=.96*logits.softmax(-1)+.04/logits.shape[-1]
                torch.testing.assert_close(factor,reference,rtol=3e-5,atol=1e-6)
            conditional=p[graph,lane,c,l,:];conditional=conditional/conditional.sum(-1,keepdim=True)
            right=stage['right_logits'][:,slots]
            torch.testing.assert_close(conditional,.96*right.softmax(-1)+.04/right.shape[-1],rtol=3e-5,atol=1e-6)
        # Decode the actual published producer token, including every null slot.
        offset=self.model.decoder.dim
        for count,decisions in [(2,sampled[0]['active']), (8,sampled[0]['pointers'][...,0]), (8,sampled[0]['pointers'][...,1])]:
            torch.testing.assert_close(token[...,offset:offset+count],
                                       (decisions[...,None]==torch.arange(count,device=self.device)).float())
            offset+=count

    def test_actual_actions_drive_next_state_without_straight_through(self):
        raw=[]
        hook=self.model.decoder.active.register_forward_hook(lambda _,args,out:raw.append(out))
        try:
            stages,token,_,records=self.rollout()
        finally:
            hook.remove()
        self.assertTrue(all(not r.prestate.requires_grad and not r.law.requires_grad for r in records))
        self.assertTrue(records[0].log_prob.requires_grad and records[0].entropy.requires_grad)
        token.retain_grad()
        loss=stages[1]['hidden'].square().mean()
        action_grad=torch.autograd.grad(loss,raw[0],allow_unused=True,retain_graph=True)[0]
        self.assertIsNone(action_grad)
        loss.backward()
        self.assertGreater(float(token.grad.abs().sum()),0)

        # Flip row 0's first actual sampled active bit; use the same independent
        # uniform draws everywhere else. Row 1's simultaneous decisions and all
        # its first-Run trajectory must stay identical; row 0's next state changes.
        first=True;draw=actor._draw
        def intervene(log_probs, gen, greedy):
            nonlocal first
            actions=draw(log_probs,gen,greedy)
            if first:
                actions=actions.clone();actions[:,0]=1-actions[:,0];first=False
            return actions
        with torch.no_grad(), patch.object(actor,'_draw',side_effect=intervene):
            altered,token2,_,records2=self.rollout()
        torch.testing.assert_close(records[0].law,records2[0].law,rtol=0,atol=0)
        torch.testing.assert_close(records[0].action[:,1],records2[0].action[:,1])
        torch.testing.assert_close(token[:,4:],token2[:,4:],rtol=0,atol=0)
        self.assertTrue((stages[0]['hidden'][:,1] != altered[0]['hidden'][:,1]).any().item())
        make_actions_changed=(records[0].action[:,0,0]!=records2[0].action[:,0,0])
        self.assertTrue(make_actions_changed.all().item())

    def test_critic_vs_full_joint_enumeration_and_own_action_independence(self):
        torch.manual_seed(83)
        critic=CentralCritic(width=32,hidden=12,rank=3).to(self.device)
        _,_,_,records=self.rollout()
        q,team,cf=critic(records)
        self.assertEqual(q.shape,(8,8));self.assertEqual(cf.shape,(8,8,2))
        self.assertFalse(team.requires_grad or cf.requires_grad)
        for ix in (0,6):
            rec=records[ix];base,terms=critic._terms(rec)
            # Brute-force the entire [B,A0,A1] joint value table as a test oracle.
            a,b=terms[:,0],terms[:,1]
            grid=base[:,None,None]+a[...,0,None]+b[:,None,:,0]
            grid=grid+(a[...,1:]@b[...,1:].transpose(-1,-2))/critic.rank**.5
            prob=rec.law.flatten(2)
            expected_team=(grid*prob[:,0,:,None]*prob[:,1,None,:]).sum((1,2))
            nleft,nright=rec.law.shape[-2:];ac,li,ri=rec.action.unbind(-1)
            ids=(ac*nleft+li)*nright+ri;batch=torch.arange(len(grid),device=self.device)
            expected0=(grid[batch,:,ids[:,1]]*prob[:,0]).sum(-1)
            expected1=(grid[batch,ids[:,0],:]*prob[:,1]).sum(-1)
            torch.testing.assert_close(q[:,ix],grid[batch,ids[:,0],ids[:,1]],rtol=3e-5,atol=2e-6)
            torch.testing.assert_close(team[:,ix,0],expected_team,rtol=3e-5,atol=2e-6)
            torch.testing.assert_close(cf[:,ix],torch.stack((expected0,expected1),-1),rtol=3e-5,atol=2e-6)
            for lane in (0,1):
                flipped=rec.action.clone();flipped[:,lane,0]=1-flipped[:,lane,0]
                _,new_team,new_cf=critic.step_values(replace(rec,action=flipped))
                torch.testing.assert_close(team[:,ix],new_team,rtol=0,atol=0)
                torch.testing.assert_close(cf[:,ix,lane],new_cf[:,lane],rtol=0,atol=0)
                self.assertGreater(float((cf[:,ix,1-lane]-new_cf[:,1-lane]).abs().max()),0)
        self.model.zero_grad(set_to_none=True)
        q.square().mean().backward()
        self.assertTrue(all(p.grad is None for p in self.model.parameters()))
        self.assertGreater(float(critic.action_terms.weight.grad.abs().sum()),0)
        policy=-torch.stack([r.log_prob for r in records],1).mean()
        policy.backward()
        self.assertGreater(float(self.model.decoder.active.weight.grad.abs().sum()),0)


if __name__=='__main__':
    torch.set_num_threads(1)
    unittest.main()
