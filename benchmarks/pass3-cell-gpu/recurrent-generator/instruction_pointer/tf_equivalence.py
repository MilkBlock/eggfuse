"""Compare individual verified targets and each connected tensor at identical initialization."""

import json
import torch
from partner_index_worlds import args
from scaling_fit import model
from scaling_pool import Pool
from joint_cell_sweep import complete_ce
from teacher_forcing import complete_nll


def check(a):
    torch.set_num_threads(1)
    cfg = {"arm": "C"}
    n, _ = model(a, cfg, 71)
    pool = Pool(a, n)
    selected = {}
    for key, w, s, ts in pool.val:
        for t in ts:
            label = ("higher" if t[0] >= w.primitives else "primitive", len(t[1]))
            selected.setdefault(label, {})
            if len(selected[label]) < 6:
                selected[label][key, t] = w, s, t
    rows = [(w, s, [t]) for group in selected.values() for w, s, t in group.values()]
    ref = None
    for device in ("reference", "cpu", "mps"):
        if device == "mps" and not torch.backends.mps.is_available():
            continue
        n, opt = model(a, cfg, 71)
        observed = []
        for k in range(0, len(rows), 4):
            batch = rows[k : k + 4]
            if device == "reference":
                losses = []
                for w, s, t in batch:
                    n.prepare(w)
                    n.physical = ("held", 0)
                    losses.append(complete_ce(n, w, n.state(w, s), t))
                y = torch.stack(losses)
            else:
                y = complete_nll(n, batch, device)
            observed.extend(y.detach().cpu().tolist())
            (y.sum() / len(rows)).backward()
        grads = {
            k: p.grad.clone() for k, p in n.named_parameters() if p.grad is not None
        }
        opt.step()
        params = {k: p.detach().clone() for k, p in n.named_parameters() if k in grads}
        result = [torch.tensor(observed), grads, params]
        if ref is None:
            ref = result
            continue
        assert grads.keys() == ref[1].keys()
        diffs = []
        for left, right in [
            (result[0], ref[0]),
            *[(grads[k], ref[1][k]) for k in grads],
            *[(params[k], ref[2][k]) for k in grads],
        ]:
            torch.testing.assert_close(left, right, rtol=2e-5, atol=5e-6)
            diffs.append((left - right).abs().max().item())
        print(
            json.dumps(
                dict(
                    device=device,
                    groups={str(k): len(v) for k, v in selected.items()},
                    tokens=len(rows),
                    nll_max=diffs[0],
                    gradient_max=max(diffs[1 : 1 + len(grads)]),
                    adam_max=max(diffs[1 + len(grads) :]),
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    check(args())
