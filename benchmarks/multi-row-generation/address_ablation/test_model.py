"""Controls for axis budgets, port visibility, selected ancestry and latent gradients."""
import unittest

import torch

from activity_ties import select
from model import ARMS, AddressModel, gather_rows


class AddressContracts(unittest.TestCase):
    def setUp(self):
        self.length, self.ports = 2, 3
        self.coords = torch.cartesian_prod(torch.arange(2), torch.arange(2), torch.arange(3))
        generator = torch.Generator().manual_seed(25)
        self.make = torch.stack([self.coords[torch.randperm(len(self.coords), generator=generator)] for _ in range(2)])
        self.finish = self.make.flip(dims=(1,))
        self.value = torch.arange(len(self.coords)).repeat(2, 1) % 3

    def model(self, arm):
        torch.manual_seed(1703)
        return AddressModel(arm, 48)

    def run_model(self, model):
        return model(self.coords, self.make, self.finish, self.value, self.length, self.ports)

    def test_activity_only_breaks_exact_address_ties(self):
        scores = torch.tensor([[[2., 2., 0.], [3., 2., 0.], [0., 1., 1.]]])
        active = torch.tensor([[False, True, True]])
        self.assertEqual(select(scores, active, False).tolist(), [[0, 0, 1]])
        self.assertEqual(select(scores, active, True).tolist(), [[1, 0, 1]])
        self.assertEqual(select(scores, torch.zeros_like(active), True).tolist(), [[0, 0, 1]])

    def test_matched_parameters_axis_budget_and_content(self):
        reference = self.model('flat').state_dict()
        for arm, axes in zip(ARMS, (1, 2, 3, 1)):
            model = self.model(arm)
            self.assertEqual(reference.keys(), model.state_dict().keys())
            for key, value in model.state_dict().items():
                torch.testing.assert_close(value, reference[key], rtol=0, atol=0)
            self.assertEqual(model.rotary.axes, axes)
            self.assertEqual(2 * axes * len(model.rotary.frequencies), 48)
            coordinates = model.rotary.coordinates(self.coords, self.length, self.ports)
            if arm in ('flat', 'two'):
                torch.testing.assert_close(coordinates[0], coordinates[1], rtol=0, atol=0)
            else:
                self.assertEqual(len(torch.unique(coordinates, dim=0)), len(self.coords))
            # Internal ports are available to all arms even if they share a
            # rotary address. The content encoder accepts previously unseen p=9.
            descriptors = model.port_content(torch.tensor([[0, 0, 0], [0, 0, 9]]), 10)
            self.assertGreater(float((descriptors[0]-descriptors[1]).detach().abs().max()), 1e-6)

    def test_wrong_learned_pointer_survives_both_gathers(self):
        model = self.model('three').eval()
        with torch.no_grad():
            for pointer in (model.first, model.second):
                for parameter in pointer.parameters():
                    parameter.zero_()
            out = self.run_model(model)
        nptr = torch.zeros_like(out['ptr1'])
        torch.testing.assert_close(out['ptr1'], nptr)
        torch.testing.assert_close(out['pair_origin'], self.coords[nptr])
        torch.testing.assert_close(out['ptr2'], torch.zeros_like(out['ptr2']))
        torch.testing.assert_close(out['result_value'], self.value[:, :1].expand_as(out['result_value']))
        self.assertTrue((out['pair_origin'] != self.make).any())

    def test_frontier_permutation_poison_and_external_scoring(self):
        with torch.no_grad():
            for arm in ARMS:
                model = self.model(arm).eval()
                out = self.run_model(model)
                address, value, latent = (out[key] for key in ('pair_origin', 'pair_value', 'pair_latent'))
                torch.testing.assert_close(address, self.coords[out['ptr1']])
                torch.testing.assert_close(value, self.value.gather(1, out['ptr1']))
                # The separate API can score a pre-existing candidate layout
                # directly. It has no legal-candidate mask or target slot input.
                pure = model.address_scores('make', self.make, self.coords, self.length, self.ports)
                torch.testing.assert_close(pure, out['scores1'])
                perm = torch.randperm(address.shape[1])
                moved = model.finish_from(address[:,perm], value[:,perm], latent[:,perm], self.finish,
                                          self.length, self.ports)
                torch.testing.assert_close(moved['scores2'], out['scores2'][...,perm], rtol=1e-5, atol=1e-6)
                torch.testing.assert_close(gather_rows(address[:,perm], moved['ptr2']),
                                           gather_rows(address, out['ptr2']))
                swapped_value = model.finish_from(address, value+10, latent, self.finish, self.length, self.ports)
                torch.testing.assert_close(swapped_value['ptr2'], out['ptr2'])
                torch.testing.assert_close(swapped_value['result_value'], out['result_value'] + 10)
                swapped_origin = address.clone()
                swapped_origin[:,0,:] = self.coords[0]
                swapped_origin[:,1,:] = self.coords[-1]
                changed = model.finish_from(swapped_origin, value, latent, self.finish, self.length, self.ports)
                self.assertGreater(float((changed['scores2']-out['scores2']).abs().max()), 1e-6)
                changed = model.finish_from(address, value, -latent, self.finish, self.length, self.ports)
                self.assertGreater(float((changed['scores2']-out['scores2']).abs().max()), 1e-6)
                with self.assertRaises(ValueError):
                    model.address_scores('finish', self.finish, address, self.length, self.ports)

    @unittest.skipUnless(torch.backends.mps.is_available(), 'Metal GPU required for device intervention')
    def test_mps_generated_bank_interventions(self):
        model = self.model('three').to('mps')
        coords, make, finish, value = [x.to('mps') for x in (self.coords, self.make, self.finish, self.value)]
        out = model(coords, make, finish, value, self.length, self.ports)
        latent = out['pair_latent']
        latent.retain_grad()
        out['scores2'].square().mean().backward()
        self.assertGreater(float(latent.grad.abs().sum()), 0)
        self.assertGreater(float(model.first.query.weight.grad.abs().sum()), 0)
        with torch.no_grad():
            origin, payload = out['pair_origin'], out['pair_value']
            perm = torch.arange(origin.shape[1]-1, -1, -1, device='mps')
            moved = model.finish_from(origin[:,perm], payload[:,perm], latent[:,perm], finish, self.length, self.ports)
            torch.testing.assert_close(moved['scores2'], out['scores2'][...,perm], rtol=1e-5, atol=1e-6)
            changed = model.finish_from(origin, payload + 17, latent, finish, self.length, self.ports)
            torch.testing.assert_close(changed['result_value'], out['result_value']+17, rtol=0, atol=0)
            torch.testing.assert_close(changed['ptr2'], out['ptr2'], rtol=0, atol=0)
            altered_origin = origin.clone()
            altered_origin[:,0,:] = coords[0]
            altered_origin[:,1,:] = coords[-1]
            changed = model.finish_from(altered_origin, payload, latent, finish, self.length, self.ports)
            self.assertGreater(float((changed['scores2']-out['scores2']).abs().max()), 1e-6)
            torch.mps.synchronize()

    def test_finish_loss_reaches_actual_generated_latent(self):
        model = self.model('two').train()
        out = self.run_model(model)
        latent = out['pair_latent']
        latent.retain_grad()
        # Use a non-symmetric score probe; this is a graph connectivity check.
        loss = out['scores2'][..., 0].square().mean()
        loss.backward()
        self.assertGreater(float(latent.grad.abs().sum()), 0)
        self.assertGreater(float(model.emit[0].weight.grad.abs().sum()), 0)
        self.assertGreater(float(model.first.query.weight.grad.abs().sum()), 0)


if __name__ == '__main__':
    torch.set_num_threads(1)
    unittest.main()
