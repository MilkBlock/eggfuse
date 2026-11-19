"""On-policy two-row rollouts and exact action-marginal baselines for Figure 05."""
from dataclasses import dataclass
import math
from pathlib import Path
import sys

import torch
from torch import nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from width_ablation.model import AliasSystem, MAX_CANDIDATES, _select


@dataclass
class StepRecord:
    run: int                    # 1 (make) or 2 (finish)
    step: int                   # 0..3 within the Run
    prestate: torch.Tensor      # [B,2,D], detached before any actions at this time
    action: torch.Tensor        # [B,2,3] sampled active, left, right
    log_prob: torch.Tensor      # [B,2], differentiable sum of all three log-probabilities
    entropy: torch.Tensor       # [B,2], differentiable exact joint entropy
    law: torch.Tensor           # [B,2,2,L,R], detached probability of every own action
    epsilon: float = 0.04

    @property
    def other_action(self):
        return self.action.flip(1)


def _log_distribution(logits, epsilon):
    if epsilon == 0:
        return logits.log_softmax(-1)
    return ((1 - epsilon) * logits.softmax(-1) + epsilon / logits.shape[-1]).log()


def _draw(log_prob, generator, greedy):
    if greedy:
        return log_prob.argmax(-1)
    # Independent uniform draws across graphs and rows. No option reads another
    # row's current action. A cumulative sum includes the final category even
    # when FP32 normalization has a small rounding error.
    with torch.no_grad():
        u = torch.rand(log_prob.shape[:-1] + (1,), device=log_prob.device, generator=generator)
        return (u >= log_prob.exp().cumsum(-1)).sum(-1).clamp_max(log_prob.shape[-1] - 1)


def _selected(log_probs, actions):
    return log_probs.gather(-1, actions.unsqueeze(-1)).squeeze(-1)


def _hard_code(actions, width, addresses, dtype):
    return (actions.unsqueeze(-1) == addresses[:width]).to(dtype)


def _sample_stage(d, left, right, left_features, right_features, ports, routes, rule_id,
                  history, run, records, generator, greedy, epsilon):
    if d.slots != 8:
        raise ValueError('expected 2 rows × 4 generated positions')
    head = d.heads[0 if d.shared_heads else rule_id]
    left_keys = head.key(left_features).transpose(1, 2)
    right_keys = head.key(right_features).transpose(1, 2)
    wire, constants = d._routes(left, right, routes)
    pool = d.pool(torch.cat((left_features.mean(1), right_features.mean(1), ports[:, 0], ports[:, 1]), -1))
    base = pool[:, None, None] + d.position.weight.reshape(2, 4, d.dim)
    previous = pool.new_zeros((len(pool), 2, d.token_width))
    left_candidates = d.condition_right(left_features)[:, None, :, :]
    columns = []
    for step in range(4):
        hidden = torch.tanh(base[:, :, step] + d.history(previous if history else torch.zeros_like(previous)))
        active_logits = d.active(hidden)
        left_logits = torch.bmm(head.query(hidden + ports[:, 0:1]), left_keys) * head.scale
        # All conditional right distributions are needed for the exact entropy
        # and action expectation. The actor picks only the slice for its own left.
        queries = hidden[:, :, None] + ports[:, 1:2, None] + left_candidates
        right_by_left = torch.matmul(head.query(queries), right_keys[:, None]) * head.scale
        log_active = _log_distribution(active_logits, epsilon)
        log_left = _log_distribution(left_logits, epsilon)
        log_all_right = _log_distribution(right_by_left, epsilon)
        active = _draw(log_active, generator, greedy)
        li = _draw(log_left, generator, greedy)
        index = li[:, :, None, None].expand(-1, -1, 1, right.shape[1])
        right_logits = right_by_left.gather(2, index).squeeze(2)
        log_right = log_all_right.gather(2, index).squeeze(2)
        ri = _draw(log_right, generator, greedy)
        log_prob = _selected(log_active, active) + _selected(log_left, li) + _selected(log_right, ri)
        log_joint = log_active[..., :, None, None] + log_left[..., None, :, None] + log_all_right[..., None, :, :]
        probabilities = log_joint.exp()
        entropy = -(probabilities * log_joint).sum(dim=(-3,-2,-1))
        action = torch.stack((active, li, ri), -1)
        records.append(StepRecord(run, step, hidden.detach(), action, log_prob, entropy, probabilities.detach(), epsilon))

        selected = torch.cat((_select(left, li), _select(right, ri)), -1)
        if constants is not None:
            selected = torch.cat((selected, constants[:, None].expand(-1, 2, -1)), -1)
        payload = selected.index_select(-1, wire)
        padded = F.pad(payload.to(hidden.dtype), (0, d.max_columns - payload.shape[-1]))
        # Hard sampled choices, including null-slot pointers, drive actual next
        # state. Only the continuous recurrent hidden has a pathwise gradient.
        previous = torch.cat((hidden, _hard_code(active, 2, d.addresses, hidden.dtype),
                              _hard_code(li, MAX_CANDIDATES, d.addresses, hidden.dtype),
                              _hard_code(ri, MAX_CANDIDATES, d.addresses, hidden.dtype), padded), -1)
        columns.append((hidden, active_logits, left_logits, right_logits, active, action[..., 1:], payload, previous))
    hidden, active_l, left_l, right_l, active, pointers, rows, tokens = (
        torch.stack(column, dim=2).flatten(1, 2) for column in zip(*columns))
    return dict(hidden=hidden, active_logits=active_l, left_logits=left_l, right_logits=right_l,
                active=active, pointers=pointers, rows=rows, fields=rows[..., 2:]), tokens


class _SamplingDecoder:
    def __init__(self, original, records, generator, greedy, epsilon):
        self.original = original
        self.records = records
        self.generator = generator
        self.greedy = greedy
        self.epsilon = epsilon
        self.run = 0

    def __getattr__(self, key):
        return getattr(self.original, key)

    def _stage(self, *args):
        self.run += 1
        return _sample_stage(self.original, *args, self.run, self.records, self.generator, self.greedy, self.epsilon)


class _RolloutView:
    """Reuse the Figure 20/04 template, certificate and make->finish code verbatim.

    Sampling changes only stage emission. This temporary view never mutates the
    model, its decoder or the greedy inference path.
    """
    resume = AliasSystem.resume

    def __init__(self, model, records, generator, greedy, epsilon):
        self.model = model
        self.decoder = _SamplingDecoder(model.decoder, records, generator, greedy, epsilon)

    def __getattr__(self, key):
        return getattr(self.model, key)


def sample_rollout(model, inputs, table, *, generator=None, greedy=False, epsilon=0.04):
    """Return ((make,finish), actual Pair tokens, relation logits, eight StepRecords).

    ``greedy`` is for numeric correspondence tests. Deployment uses the original
    WidthSystem 2x4 forward directly. No labels or reward enter this interface.
    """
    records = []
    if not 0 <= epsilon <= 1:
        raise ValueError('epsilon must be in [0,1]')
    view = _RolloutView(model, records, generator, greedy, epsilon)
    stages, token, relations = AliasSystem.forward(view, *inputs, table)
    return stages, token, relations, records


class CentralCritic(nn.Module):
    """Fit Q(s,a0,a1) on observed joint returns and integrate the action law exactly.

    Q = base(s) + u0(s,a0) + u1(s,a1) + dot(f0(s,a0), f1(s,a1))/sqrt(rank).
    This low-rank restriction permits both the team and counterfactual expectations
    in O(number of single-row actions) under the two rows' conditional independence.
    Both arms run identical computations. Only the selected detached baseline changes.
    """

    def __init__(self, width=32, hidden=32, rank=8):
        super().__init__()
        self.rank = rank
        self.network = nn.Sequential(nn.Linear(2*width + 6, hidden), nn.Tanh(),
                                     nn.Linear(hidden, hidden), nn.Tanh())
        self.base = nn.Linear(hidden, 1)
        self.action_terms = nn.Linear(hidden, 2 * 2 * MAX_CANDIDATES**2 * (rank+1))
        self.register_buffer('times', torch.eye(4), persistent=False)
        self.register_buffer('runs', torch.eye(2), persistent=False)

    def _terms(self, record):
        batch = record.prestate.shape[0]
        time = self.times[record.step].expand(batch, -1)
        run = self.runs[record.run - 1].expand(batch, -1)
        state = self.network(torch.cat((record.prestate.detach().flatten(1), run, time), -1))
        _, _, _, left, right = record.law.shape
        all_terms = self.action_terms(state).reshape(batch, 2, 2, MAX_CANDIDATES, MAX_CANDIDATES, self.rank+1)
        eligible = all_terms[:, :, :, :left, :right].reshape(batch, 2, 2*left*right, self.rank+1)
        return self.base(state).squeeze(-1), eligible

    def _payoff(self, base, left, right):
        interaction = (left[..., 1:] * right[..., 1:]).sum(-1) / math.sqrt(self.rank)
        return base + left[..., 0] + right[..., 0] + interaction

    def step_values(self, record):
        base, eligible = self._terms(record)
        left, right = record.law.shape[-2:]
        active, li, ri = record.action.unbind(-1)
        ids = (active * left + li) * right + ri
        index = ids.unsqueeze(-1).unsqueeze(-1).expand(-1, -1, 1, self.rank + 1)
        actual = eligible.gather(2, index).squeeze(2)
        q = self._payoff(base, actual[:, 0], actual[:, 1])
        with torch.no_grad():
            expected = (record.law.detach().flatten(2).unsqueeze(-1) * eligible).sum(2)
            team = self._payoff(base, expected[:, 0], expected[:, 1])[:, None].expand(-1, 2)
            counterfactual = torch.stack((self._payoff(base, expected[:, 0], actual[:, 1]),
                                          self._payoff(base, actual[:, 0], expected[:, 1])), -1)
        return q, team, counterfactual

    def forward(self, records):
        """Return actual Q [B,steps], detached V and b_i [B,steps,2]."""
        values = [self.step_values(record) for record in records]
        return tuple(torch.stack(column, 1) for column in zip(*values))
