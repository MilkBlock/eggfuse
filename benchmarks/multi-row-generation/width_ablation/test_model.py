"""Width, scheduling equivalence and generated-history contracts for Figure 04."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

import torch

from model import AliasSystem, FIG20, INPUTS, WidthSystem
from encoder import EClassSchema
sys.path.insert(0, str(FIG20.parent))
from eclass_ablation.data import dataset


class WidthContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.device = torch.device(os.environ.get('WIDTH_TEST_DEVICE', 'cpu'))
        templates = json.loads((FIG20/'corpus/manifest.json').read_text())['templates']
        train = [t for t in templates if t['split'] == 'train']
        cls.schema = EClassSchema(train)
        source = dataset('train', train[0], 8)
        cls.inputs = tuple(torch.as_tensor(source[k], dtype=torch.int32, device=cls.device) for k in INPUTS)
        cls.bank = cls.schema.bank(train[0], 'pairwise', cls.device)

    def setUp(self):
        self.parent = AliasSystem(self.schema, 1703).eval()
        checkpoint = os.environ.get('WIDTH_TEST_PARENT')
        if checkpoint:
            self.parent.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True))
        self.model = WidthSystem(self.schema, 1703).eval()
        self.initial_positions = {s:self.model.state_dict()[f'decoder.{s}.projection.weight'].clone()
                                  for s in ('position','source_position')}
        self.model.load_fig20(self.parent.state_dict())
        self.parent.to(self.device); self.model.to(self.device)
        with torch.no_grad():
            self.table = self.parent.encoder.encode_bank(self.bank)

    def compare(self, a, b):
        for left, right in zip(a[0], b[0]):
            for key in left:
                if key in ('active', 'pointers', 'fields', 'rows'):
                    torch.testing.assert_close(left[key], right[key], rtol=0, atol=0)
                else:
                    torch.testing.assert_close(left[key], right[key], rtol=3e-4, atol=3e-5)
        for left, right in zip(a[1:], b[1:]):
            torch.testing.assert_close(left, right, rtol=3e-4, atol=3e-5)

    def test_checkpoint_conversion_and_coordinate_capacity(self):
        shared = self.model.state_dict()
        original = self.parent.state_dict()
        for key in original.keys() & shared.keys():
            torch.testing.assert_close(original[key], shared[key], rtol=0, atol=0)
        self.assertEqual(original.keys() - shared.keys(), {'decoder.position.weight','decoder.source_position.weight'})
        self.assertEqual(shared.keys() - original.keys(),
                         {'decoder.position.projection.weight','decoder.source_position.projection.weight'})
        for name in ('position', 'source_position'):
            coord = getattr(self.model.decoder, name)
            self.assertEqual(coord.features.shape, (8,4))
            self.assertEqual(torch.linalg.matrix_rank(coord.features.cpu().double()).item(), 4)
            torch.testing.assert_close(coord.projection.weight.detach().cpu(),self.initial_positions[name],rtol=0,atol=0)

    @torch.no_grad()
    def test_one_lane_matches_fig20_with_old_positions(self):
        # Isolate rescheduling from the deliberate Fourier coordinate change.
        self.model.decoder.position = copy.deepcopy(self.parent.decoder.position)
        self.model.decoder.source_position = copy.deepcopy(self.parent.decoder.source_position)
        parent = self.parent(*self.inputs, self.table)
        actual = self.model(*self.inputs, self.table, rows=1)
        self.compare(parent, actual)

    @torch.no_grad()
    def test_parallel_matches_serial_lanes_and_replays_make_token(self):
        for rows in (1,2,4):
            actual = self.model(*self.inputs, self.table, rows=rows)
            serial = self.model(*self.inputs, self.table, rows=rows, schedule='serial_lanes')
            self.compare(actual, serial)
            make, finish = actual[0]
            token = actual[1]
            self.assertEqual(make['active'].shape, (len(token),8))
            self.assertEqual(finish['active'].shape, (len(token),8))
            a,b,req,a_port,rport,phase,comm,external,eport=self.inputs
            cond = self.model.operand[1].expand(len(token),-1,-1)
            resumed, relation = self.model.resume(token,req,rport,phase,comm,external,eport,self.table,cond,rows=rows)
            for key in finish:torch.testing.assert_close(resumed[key],finish[key],rtol=0,atol=0)
            torch.testing.assert_close(relation,actual[2],rtol=0,atol=0)

    @torch.no_grad()
    def test_change_only_consumer_width(self):
        first = self.model(*self.inputs,self.table,rows=(1,1))
        mixed = self.model(*self.inputs,self.table,rows=(1,4))
        torch.testing.assert_close(first[1],mixed[1],rtol=0,atol=0)
        for key in first[0][0]:
            torch.testing.assert_close(first[0][0][key],mixed[0][0][key],rtol=0,atol=0)
        self.assertGreater(float((first[0][1]['hidden']-mixed[0][1]['hidden']).abs().max()),1e-6)
        q=self.model.operand[1].expand(len(mixed[1]),-1,-1)
        _,_,requests,_,rport,phase,comm,external,eport=self.inputs
        resumed,_=self.model.resume(first[1],requests,rport,phase,comm,external,eport,self.table,q,rows=4)
        for key in resumed:
            torch.testing.assert_close(resumed[key],mixed[0][1][key],rtol=0,atol=0)
        other = self.model(*self.inputs,self.table,rows=(4,1))
        self.assertGreater(float((first[1]-other[1]).abs().max()),1e-6)

    @torch.no_grad()
    def test_history_is_generated_per_lane_and_does_not_cross(self):
        for rows in (2,4):
            length = 8 // rows
            seen = []
            module = self.model.decoder.history
            hook = module.register_forward_pre_hook(lambda _, args: seen.append(args[0].clone()))
            try:
                actual = self.model(*self.inputs,self.table,rows=rows)
            finally:
                hook.remove()
            token = actual[1][...,:-1]
            self.assertEqual(len(seen),2*length)
            self.assertEqual(seen[0].shape, (len(token),rows,self.model.decoder.token_width))
            for t in range(1,length):
                torch.testing.assert_close(seen[t],token[:,t-1::length],rtol=0,atol=0)

            calls = 0
            def erase_one_lane(_, args):
                nonlocal calls
                calls += 1
                if calls == 2:  # make, second position
                    altered=args[0].clone();altered[:,1]=0
                    return (altered,)
                return None
            hook = module.register_forward_pre_hook(erase_one_lane)
            try:
                changed = self.model(*self.inputs,self.table,rows=rows)
            finally:
                hook.remove()
            old = actual[0][0]['hidden'].reshape(len(token),rows,length,-1)
            new = changed[0][0]['hidden'].reshape(len(token),rows,length,-1)
            torch.testing.assert_close(old[:,0],new[:,0],rtol=0,atol=0)
            torch.testing.assert_close(old[:,:,0],new[:,:,0],rtol=0,atol=0)
            self.assertGreater(float((old[:,1,1]-new[:,1,1]).abs().max()), 1e-6)
            if rows>2:torch.testing.assert_close(old[:,2:],new[:,2:],rtol=0,atol=0)
            blind = self.model(*self.inputs,self.table,rows=rows,schedule='zero_history')
            blind_hidden=blind[0][0]['hidden'].reshape_as(old)
            torch.testing.assert_close(old[:,:,0], blind_hidden[:,:,0], rtol=0, atol=0)
            self.assertTrue(torch.any(old[:,:,1:] != blind_hidden[:,:,1:]).item())

    def test_second_run_gradients_to_emitted_make_tokens(self):
        model=self.model.train()
        stages,token,_=model(*self.inputs,self.table,rows=4)
        token.retain_grad()
        stages[1]['left_logits'].square().mean().backward()
        self.assertGreater(token.grad.abs().sum().item(),0)
        self.assertGreater(model.decoder.history.weight.grad.abs().sum().item(),0)
        self.assertGreater(model.decoder.position.projection.weight.grad.abs().sum().item(),0)


if __name__=='__main__':
    torch.set_num_threads(1)
    unittest.main()
