"""Replay one training decision with and without its higher Cell on the same sealed prefix."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from alternate_proofs import digest
from anchor_set_audit import load_actor
from higher_cell import read
from layout_credit import CreditIssuer, load_policy
from layout_credit_report import verify
from online import execute
from prefix_policy import Policy
from prefix_recovery import Recovery


class ForkIssuer(CreditIssuer):
    def __init__(self, *args, stop_graph=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop_graph = stop_graph
        self.history_digest = hashlib.sha256()
        self.decisions = {}

    def record(self, x):
        self.history_digest.update(json.dumps(x, sort_keys=True, separators=(',', ':')).encode())
        self.history_digest.update(b'\n')

    def batch(self, frame, history, snap, roots, next_token):
        self.record([frame[k] for k in ('run', 'rules', 'updates', 'retired', 'accepted', 'layout_feedback')])
        return super().batch(frame, history, snap, roots, next_token)

    def choose_layout(self, req, options, context):
        uid = super().choose_layout(req, options, context)
        self.record([req, uid])
        token = req['token']
        if uid is not None:
            self.decisions[token] = (req['run'], uid, self.history_digest.hexdigest())
        return None if token == self.stop_graph else uid


def compare(root, donor, binary, weights, baked, policy, recovery, gold, name):
    study = read(baked/'study.json')
    if name not in study['training'] or digest(weights) != study['root_weights']:
        raise ValueError('fork diagnosis requires a training program and its frozen root Actor')
    folder = root/name
    program = read(folder/'program.json')
    reference = read(folder/'capture.json')
    seed = 1703 + next(row['seed'] for row in read(root/'manifest.json') if row['directory'] == name)
    actor = load_actor(weights, True)
    choice = load_policy(policy, baked)
    prefix = Policy(32, recovery=Recovery(recovery, weights))
    def episode(token):
        issuer = ForkIssuer(actor, donor, program, baked, omit=True, explore=False, seed=seed,
                            policy=choice, attach=True, stop_graph=token)
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'layouts.json'
            path.write_text(json.dumps(issuer.receiver_layouts(), separators=(',', ':')))
            run = execute(binary, folder/'program.json', actor, seed, assist=True, audit_ept=True,
                          prefix_policy=prefix, graph_issuer=issuer, layout_file=path)
        for src, dst in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes'),
                         ('resume_audit','resumes'),('event_audit','events')]:
            if run[src] != reference[dst]:
                raise ValueError('fork changed source execution in '+dst)
        verify(dict(execution=run, reference_commits=reference['matches']), gold)
        returns, credit = issuer.credit(run['ept'])
        return issuer, returns, dict(signed=run['counts']['accepted'], paid=run['issued'],
                   effective=sum(run['ept']['signed_external'] + run['ept']['signed_internal']),
                   omitted_valid=credit['omitted_valid_packets'], state=run['state_sha'])
    issuer, returns, original = episode(None)
    # Intentionally select illustrative realized successes. Their treatment
    # effects do not estimate the population average of a random intervention.
    selected = []
    for criterion in ('owned_valid', 'uncontested_effects'):
        possible = [t for t, c in returns.items() if c[criterion] > 0 and t not in selected]
        if possible:
            selected.append(max(possible, key=lambda t: (returns[t][criterion], -t)))
    if not selected:
        raise ValueError('no native ownership or effective operation to intervene on')
    forks = []
    for token in selected:
        control, _, standalone = episode(token)
        if control.decisions.get(token) != issuer.decisions[token]:
            raise ValueError('standalone intervention did not start at the same decision')
        run, uid, prefix_sha = issuer.decisions[token]
        forks.append(dict(token=token, run=run, layout=uid, size=len(issuer.layouts[uid]), prefix=prefix_sha,
                          child_credit=returns[token], standalone=standalone,
                          graph_minus_standalone={k: original[k]-standalone[k] for k in
                                                  ('signed','paid','effective','omitted_valid')}))
    return dict(mode='native assist single-decision fork', program=name, binary=digest(binary),
                weights=digest(weights), catalog=study['catalog_sha'], policy=choice.checkpoint,
                recovery=prefix.recovery.checkpoint, original=original, forks=forks)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','binary','weights','baked','policy','recovery','gold','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--case',required=True)
    a = p.parse_args()
    torch.set_num_threads(1)
    result = compare(a.root,read(a.donor/'program.json'),a.binary,a.weights,a.baked,a.policy,
                     a.recovery, read(a.gold/(a.case+'.json')), a.case)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
