import unittest
from types import SimpleNamespace

import numpy as np
import torch

from continuation_data import boundary, examples
from discrete_draft import Cell
from resident_page import shader


class RunContinuation(unittest.TestCase):
    def test_missing_witness_is_not_run_exhaustion(self):
        self.assertEqual(boundary(2, 4, True), "page_budget")
        self.assertEqual(boundary(4, 4, False), "stream_evidence_exhausted")
        self.assertEqual(boundary(4, 4, True), "teacher_run_exhausted")

    def test_censor_only_the_unobserved_tail(self):
        z = torch.zeros(32)
        m = SimpleNamespace(state=z, event=z, embed=lambda _: z)
        for kind, mask in [
            ("page_budget", 0),
            ("teacher_run_exhausted", 1),
            ("stream_evidence_exhausted", 0),
        ]:
            _, first, end = list(
                examples(m, [], [Cell(0, ())], kind, np.random.default_rng(2))
            )
            self.assertEqual(first[2][0, 0], 1)
            self.assertEqual(end[2].sum(), 0)
            self.assertEqual(end[3][-1, 0], mask)
            self.assertEqual(end[3][0, 1], 1)

    @unittest.skipUnless(torch.backends.mps.is_available(), "requires Metal")
    def test_supervised_gpu_job_commands_match_existing_editor(self):
        import torch.nn.functional as F

        inputs = torch.tensor(
            [[0.7, -1.0, 2.0], [1.9, 2.0, 1.0], [-2.0, 3.0, -1.0]], dtype=torch.float32
        )
        golden = []
        for i, row in enumerate(inputs):
            action = int(torch.cat((torch.zeros(1), row[1:])).argmax())
            if i < 2 and action:
                golden.append([i, action])
            golden.extend([[i, 0]] * int(F.softplus(row[0]).round()))
        config = torch.tensor(
            [8, 1, 1, 1, 1, 1, 1, 0, 7, -1, 136, 16], dtype=torch.int32, device="mps"
        )
        control = torch.tensor([2] + [0] * 16, dtype=torch.int32, device="mps")
        jobs = torch.zeros((16, 2), dtype=torch.int32, device="mps")
        shader(136).jobs(inputs.to("mps"), control, jobs, config, threads=1)
        self.assertEqual(jobs[: len(golden)].cpu().tolist(), golden)
