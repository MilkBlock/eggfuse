"""Train a conditional read address using synthetic pairs of token receipts."""
import torch


def fit_address(correlated=False, width=8, steps=80):
    # Labels name the partner's memory address. The latent field/role action
    # has no label: any projection yielding that address receives credit.
    rng = torch.Generator().manual_seed(518)
    with torch.random.fork_rng():
        torch.manual_seed(518)
        policy = torch.nn.Sequential(torch.nn.Embedding(2, width), torch.nn.Tanh(),
                                     torch.nn.Linear(width, 8))
    roles = torch.arange(512) % 2
    fields = torch.randint(0, 1 << 16, (512, 4), generator=rng)
    if correlated:
        fields[:, 1] = fields[:, 0]
    addresses = fields[:, None, :].expand(-1, 2, -1)
    correct = ((torch.arange(2)[None, :, None] != roles[:, None, None]) &
               (addresses == fields[:, :1, None])).flatten(1)
    opt = torch.optim.Adam(policy.parameters(), lr=.03)
    for _ in range(steps):
        opt.zero_grad()
        logp = policy(roles).log_softmax(1)
        loss = -logp.masked_fill(~correct, -torch.inf).logsumexp(1).mean()
        loss.backward()
        opt.step()
    logits = policy(torch.arange(2)).detach()
    return dict(routes=[list(divmod(action, 4)) for action in logits.argmax(1).tolist()],
                logits=logits.tolist(), width=width, steps=steps, correlated=correlated)
