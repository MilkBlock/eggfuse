"""Check graph relabeling, pooled/port readouts and the unseen-ID contract."""

import copy
import unittest
import torch
from study import Study
from encoders import TemplateEncoder


class Encoding(unittest.TestCase):
    def test_relabel_and_unseen(self):
        study = Study()
        template = study.held[0]
        device = "mps"
        spec = study.schema.pack(template, device)
        self.assertEqual(int(spec.identity), 0)
        reordered = copy.deepcopy(template)
        g = reordered["graph"]
        n = len(g["nodes"])
        g["nodes"] = list(reversed(g["nodes"]))
        g["edges"] = [[n - 1 - i, r, n - 1 - j] for i, r, j in g["edges"]]
        g["readouts"] = [[n - 1 - i for i in row] for row in g["readouts"]]
        perm = study.schema.pack(reordered, device)
        for variant in ("id", "roles", "pooled", "ports"):
            torch.manual_seed(1703)
            encoder = TemplateEncoder(study.schema, 32, variant).to(device)
            result = encoder(spec)
            torch.testing.assert_close(result, encoder(perm), rtol=1e-5, atol=1e-5)
            assert result.shape == (2, 2, 32)

    def test_only_readout_changes(self):
        st = Study()
        g = st.schema.pack(st.train[0], "mps")
        a = TemplateEncoder(st.schema, 32, "pooled").to("mps")
        b = TemplateEncoder(st.schema, 32, "ports").to("mps")
        b.load_state_dict(a.state_dict())
        self.assertGreater(float((a(g) - b(g)).detach().abs().max()), 1e-4)
        self.assertTrue(torch.isfinite(a(g)).all())


if __name__ == "__main__":
    unittest.main()
